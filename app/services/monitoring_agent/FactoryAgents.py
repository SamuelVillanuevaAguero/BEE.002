"""
"""

from app.services.monitoring_agent.GenericMonitoring import GenericMonitoring

class FactoryAgents:
    _instances = {}

    @classmethod
    def create(cls, name: str = None):
        return cls._instances.get(name, GenericMonitoring)