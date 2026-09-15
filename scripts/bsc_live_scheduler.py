"""Production scheduling adapter; preserves the recorded neural source and policy.
Finish pending operations first, then prioritize executable neural signals over
starting another tax/bridge batch. Build commits against a post-observation block.
"""
import time
from flyterm.ops.keeper import Keeper as BaseKeeper
from flyterm.ops.state import Snapshot
from flyterm.ops.planner import hyper_step, action
from flyterm.ops.certificates import typed, sign, commit_call


class Keeper(BaseKeeper):
    def _submit_model(self, snap, cfg, message):
        registry = cfg['addresses']['registry']
        doc = typed('Commit', cfg['chainId'], registry, message)
        if not self.live:
            return {'state': 'COMMIT_PLAN', 'typedData': doc, 'signingEnabled': False}
        signature = sign(doc, self._key('modelKeyFileEnv'), self.config['modelSigner'])
        return self._submit('hyper', {'kind': 'model_commit', 'intent': {
            'chainId': cfg['chainId'], 'to': registry, 'value': '0',
            'data': commit_call(message, signature)}})

    def _context(self, hyper):
        self.snapshots = {
            name: hyper if name == 'hyper' else Snapshot(rpc, account_version=self.config['chains'][name].get('accountVersion', 3))
            for name, rpc in self.rpcs.items()}

    def step(self):
        # The original executor owns nonce recovery and every pending receipt.
        if not self.brain or any(self.j.pending(c['chainId'], c['signerAddress']) for c in self.config['chains'].values()):
            return super().step()
        cfg = self.config['chains']['hyper']
        snap = Snapshot(self.rpcs['hyper'], account_version=cfg.get('accountVersion', 3))
        if not -30 <= int(time.time()) - snap.timestamp <= 90:
            return super().step()
        plan = hyper_step(snap, cfg)
        if plan.get('wait') != 'model_observation':
            return super().step()
        state = plan['snapshot']
        if state['core']['equityE6'] <= 0:
            return super().step()
        registry = cfg['addresses']['registry']
        nonce = snap.get(registry, 'nonce()', ['uint64'])
        side = snap.get(registry, 'side()', ['uint8'])
        if (nonce > state['lastCommit']
                and snap.get(registry, 'deadline()', ['uint64']) >= snap.timestamp
                and self._model_actionable(snap, cfg, state, side)):
            self._context(snap)
            return self._submit('hyper', action(cfg['chainId'], cfg['addresses']['account'],
                'execute(uint64)', ['uint64'], [nonce], 'model_execute'))
        window = int(time.time()) // 60
        if getattr(self, '_model_window', None) == window:
            return super().step()
        self.brain.observe(state)
        # A block captured before market fetching can predate the recorded input.
        # Refresh it; never alter observation timestamps or relax commit expiry.
        fresh = Snapshot(self.rpcs['hyper'], account_version=cfg.get('accountVersion', 3))
        if not -30 <= int(time.time()) - fresh.timestamp <= 90:
            return super().step()
        current = hyper_step(fresh, cfg)
        if current.get('wait') != 'model_observation':
            return super().step()
        message = self.brain.commit(fresh, cfg)
        self._model_window = window
        if message is not None:
            actionable = self._model_actionable(fresh, cfg, current['snapshot'], message['side'])
            if actionable or message['toRound'] - message['fromRound'] + 1 >= cfg['anchorEveryRounds']:
                self._context(fresh)
                return self._submit_model(fresh, cfg, message)
        return super().step()
