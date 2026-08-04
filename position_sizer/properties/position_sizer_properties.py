# QUANTDEMY - https://quantdemy.com - Trading con Python y MetaTrader 5: Crea tu Propio Framework

from pydantic import BaseModel

class BaseSizingProps(BaseModel):
    pass

class MinSizingProps(BaseSizingProps):
    pass

class FixedSizingProps(BaseSizingProps):
    """
    Represents the properties for fixed sizing of positions.

    Attributes:
        volume (float): The fixed volume for each position.
    """
    volume: float

class RiskPctSizingProps(BaseSizingProps):
    """
    Properties for risk percentage position sizing.

    Attributes:
        risk_pct (float): The risk percentage for position sizing.
    """
    risk_pct: float