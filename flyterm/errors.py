class ObserverRestartRequired(RuntimeError):
    """A model mutation was not fully persisted; restart from the durable journal."""
