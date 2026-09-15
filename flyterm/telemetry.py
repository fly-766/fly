"""Read-only, bounded full-model sampling. No prices, policies or trade actions."""
import io
import json
from contextlib import contextmanager

import numpy as np

from .records import canonical, digest

SCHEMA = "flyterm-neural-telemetry/v1"
GROUPS = ("retina", "relay", "kc", "mbon", "dopamine", "readout", "other")


class NeuralSampler:
    def __init__(self, model, max_nodes=128, max_edges=256):
        self.model = model
        self.brain = b = model.controller.brain
        decoder = model.controller.decoder
        self.members = {
            "retina": np.unique(np.concatenate([b.retina, b.r8])).astype(np.int32),
            "relay": np.asarray(b.lamina, dtype=np.int32),
            "kc": np.asarray(b.circuit["kc"], dtype=np.int32),
            "mbon": np.asarray(b.circuit["mb"], dtype=np.int32),
            "dopamine": np.asarray(b.circuit["dan"], dtype=np.int32),
            "readout": np.unique(np.concatenate([decoder.left, decoder.right, decoder.gate])).astype(np.int32),
        }
        # Membership is for display only; simulation always retains the full graph.
        classification=np.full(b.n,"other",dtype="<U8")
        for group in ("relay","retina","kc","mbon","dopamine","readout"):
            classification[self.members[group]]=group
        self.members={g:np.flatnonzero(classification==g) for g in GROUPS}
        chosen, tags = [], {}

        def add(indices, group, count):
            ordered = sorted(set(map(int, indices)), key=lambda i: int(b.ids[i]))
            if len(ordered) > count:
                ordered = [ordered[i] for i in np.linspace(0, len(ordered)-1, count, dtype=int)]
            for index in ordered:
                if index not in tags and len(chosen) < max_nodes:
                    chosen.append(index); tags[index] = str(classification[index])

        add(self.members["readout"], "readout", 8)
        add(self.members["dopamine"], "dopamine", 20)
        add(self.members["mbon"], "mbon", 8)
        add(np.unique(b.circuit["pre"]), "kc", 24)
        add(b.retina, "retina", 14)
        add(b.r8, "retina", 8)
        add(b.lamina, "relay", 14)
        # Add actual immediate neighbors to make real display connections visible.
        for index in list(chosen):
            if tags[index] != "retina": continue
            neighbors = b.post[b.ptr[index]:b.ptr[index+1]]
            add(neighbors, "relay", 2)
        add(np.arange(b.n), "other", max_nodes)
        if len(chosen) < min(max_nodes, b.n):
            for index in np.argsort(b.ids):
                add([index], "other", 1)
                if len(chosen) >= min(max_nodes, b.n): break
        self.indices = np.asarray(chosen, dtype=np.int32)
        local = {index: i for i, index in enumerate(chosen)}
        plastic = set(map(int, b.circuit["edges"]))
        edges = []
        for pre in chosen:
            for e in range(int(b.ptr[pre]), int(b.ptr[pre+1])):
                post = int(b.post[e])
                if post in local:
                    edges.append((e, pre, post))
        edges.sort(key=lambda item: (item[0] not in plastic, item[0]))
        edges = edges[:max_edges]
        self.edge_indices = np.asarray([e for e, _, _ in edges], dtype=np.int64)
        reward, aversive = set(map(int, b.circuit["reward"])), set(map(int, b.circuit["aversive"]))
        left, right, gate = map(lambda x: set(map(int,x)), (decoder.left, decoder.right, decoder.gate))
        def label(i):
            if i in reward: return "PAM11"
            if i in aversive: return "PPL101"
            if i in left: return "DNp20 L"
            if i in right: return "DNp20 R"
            if i in gate: return "DNpe017"
            return {"retina":"Visual input", "relay":"Visual relay", "kc":"KC", "mbon":"MBON", "other":"Other neuron"}.get(tags[i],tags[i])
        self.topology = {
            "nodes": [{"id":str(int(b.ids[i])), "index":i, "group":tags[i], "label":label(i)} for i in chosen],
            "edges": [{"index":e, "source":local[pre], "target":local[post], "plastic":e in plastic} for e,pre,post in edges],
            "groupSizes":{g:len(v) for g,v in self.members.items()},
            "totalNeurons":int(b.n), "totalConnections":len(b.post),
            "selection":"fixed-ids-and-existing-edges/v1", "layout":"functional-schematic-not-anatomical",
        }
        self.topology["hash"] = digest(self.topology)
        self._capturing = False

    @contextmanager
    def capture(self):
        if self._capturing: raise RuntimeError("Nested neural telemetry sampling")
        b = self.brain
        original = b.step
        had_override = "step" in b.__dict__
        old_override = b.__dict__.get("step")
        start = float(b.sim_ms)
        capture = {"startMs":start, "times":[], "spikes":[], "voltage":[], "weights":[], "groups":[],
                   "weightBefore":b.weight[self.edge_indices].copy()}
        def sampled(*args, **kwargs):
            counts, wall = original(*args, **kwargs)
            capture["times"].append(round(float(b.sim_ms)-start, 4))
            capture["spikes"].append(counts[self.indices].copy())
            capture["voltage"].append(b.v[self.indices].copy())
            capture["weights"].append(b.weight[self.edge_indices].copy())
            capture["groups"].append([int(np.sum(counts[self.members[g]], dtype=np.int64)) for g in GROUPS])
            return counts, wall
        self._capturing = True
        b.step = sampled
        try:
            yield capture
        finally:
            if had_override: b.step = old_override
            else: del b.step
            self._capturing = False

    def artifact(self, journal, capture, *, run_id, sequence, output):
        if not capture["times"]: raise ValueError("No neural bins captured")
        b = self.brain
        counts = b.counts
        metadata = {
            "schema":SCHEMA, "runId":run_id, "sequence":sequence, "topology":self.topology,
            "groupOrder":GROUPS, "windowMs":float(b.sim_ms)-capture["startMs"],
            "brainStartMs":capture["startMs"], "brainEndMs":float(b.sim_ms),
            "binMeaning":"spike counts within bin; membrane voltage and weight at bin end",
            "summary":{"totalSpikes":int(counts.sum()), "activeNeurons":int(np.count_nonzero(counts)),
                       "kcSpikes":int(output.get("KC_spikes",0)), "rewardSpikes":int(output.get("reward_spikes",0)),
                       "aversiveSpikes":int(output.get("aversive_spikes",0)), "memory":output.get("memory",{}),
                       "leftHz":float(output.get("left_hz",0)), "rightHz":float(output.get("right_hz",0)),
                       "differenceHz":float(output.get("difference_hz",0)), "side":output.get("side","HOLD")},
        }
        arrays = {k:np.asarray(capture[k]) for k in ("times","spikes","voltage","weights","groups","weightBefore")}
        if any(not np.isfinite(a).all() for a in arrays.values()): raise ValueError("Nonfinite telemetry")
        stream = io.BytesIO()
        np.savez_compressed(stream, metadata=canonical(metadata).decode(), **arrays)
        return journal.artifact(stream.getvalue(), ".npz")


def unpack(path):
    if path.stat().st_size > 2_000_000: raise ValueError("Telemetry artifact too large")
    import zipfile
    with zipfile.ZipFile(path) as archive:
        if sum(info.file_size for info in archive.infolist())>8_000_000:raise ValueError("Expanded telemetry too large")
    with np.load(path, allow_pickle=False) as archive:
        data = json.loads(str(archive["metadata"]))
        if data.get("schema") != SCHEMA: raise ValueError("Unknown telemetry schema")
        n, e = len(data["topology"]["nodes"]), len(data["topology"]["edges"])
        times = archive["times"]
        if not 0 < n <= 128 or not 0 <= e <= 256 or not 0 < len(times) <= 100: raise ValueError("Unbounded telemetry")
        shapes={"spikes":(len(times),n),"voltage":(len(times),n),"weights":(len(times),e),"groups":(len(times),len(GROUPS)),"weightBefore":(e,)}
        for key,shape in shapes.items():
            a=archive[key]
            if a.shape != shape or not np.isfinite(a).all(): raise ValueError("Invalid telemetry shape")
            data[key]=np.round(a,3).tolist() if key=="voltage" else a.tolist()
        data["times"]=times.tolist()
        return data
