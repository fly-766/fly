"""AgentKit ActionProvider for Coinbase Advanced (an exchange, not CDP wallet).

The public Action objects are invoked directly by the fixed neural decoder.
No LLM, general wallet tools, transfers, or AgentKit analytics decorator.
"""

import time
from typing import Literal

from coinbase_agentkit import ActionProvider
from coinbase_agentkit.action_providers.action_provider import Action
from pydantic import BaseModel, ConfigDict


class Proposal(BaseModel):
    model_config = ConfigDict(extra="forbid")
    product: str
    side: Literal["BUY", "SELL"]


class StonkflyActions(ActionProvider):
    def __init__(self, guard, broker):
        self.guard = guard
        self.broker = broker
        self.quotes = {}
        super().__init__("stonkfly", [])

    def supports_network(self, network):
        return getattr(network, "network_id", None) == "coinbase-advanced"

    def get_actions(self, wallet_provider=None):
        return [
            Action(
                name="stonkfly_spot_order",
                description="Submit a budget-checked, price-bounded Coinbase Advanced spot FOK order from a neural proposal.",
                args_schema=Proposal,
                invoke=self.invoke,
            )
        ]

    def invoke(self, args):
        p = Proposal.model_validate(args)
        plan = self.guard.plan(p.product, p.side, self.quotes)
        plan["neural_observation"] = self.guard.l.get("observation")
        plan["checkpoint"] = self.guard.l.get("checkpoint")
        plan = self.guard.l.reserve(plan, time.time())
        return self.broker.execute(plan, self.guard.before_submit)
