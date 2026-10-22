# API Reference

## Configuration

```{eval-rst}
.. autoclass:: orion_finance_sdk_py.contracts.OrionConfig
   :members:
   :undoc-members:
   :show-inheritance:
```

## Vaults

```{eval-rst}
.. autoclass:: orion_finance_sdk_py.contracts.OrionVault
   :members:
   :undoc-members:
   :show-inheritance:

.. autoclass:: orion_finance_sdk_py.contracts.OrionTransparentVault
   :members:
   :undoc-members:
   :show-inheritance:
```

## Factory

```{eval-rst}
.. autoclass:: orion_finance_sdk_py.contracts.VaultFactory
   :members:
   :undoc-members:
   :show-inheritance:
```

## Liquidity Orchestrator

```{eval-rst}
.. autoclass:: orion_finance_sdk_py.contracts.LiquidityOrchestrator
   :members:
   :undoc-members:
   :show-inheritance:
```

## Price Adapter Registry

```{eval-rst}
.. autoclass:: orion_finance_sdk_py.contracts.PriceAdapterRegistry
   :members:
   :undoc-members:
   :show-inheritance:
```

## Execution cost

```{eval-rst}
.. autoclass:: orion_finance_sdk_py.costs.types.ExecutionCost
   :members:
   :undoc-members:

.. autoclass:: orion_finance_sdk_py.costs.estimator.ExecutionCostEstimator
   :members:
   :undoc-members:

.. autofunction:: orion_finance_sdk_py.costs.estimator.get_cost
```

## Return statistics

```{eval-rst}
.. autoclass:: orion_finance_sdk_py.stats.series.ReturnSeries
   :members:
   :undoc-members:

.. autoclass:: orion_finance_sdk_py.stats.ranking.RankingMetrics
   :members:
   :undoc-members:

.. autofunction:: orion_finance_sdk_py.stats.ranking.rank_products

.. autofunction:: orion_finance_sdk_py.stats.ranking.expanding_sasr

.. autofunction:: orion_finance_sdk_py.stats.ranking.ranking_metrics

.. autofunction:: orion_finance_sdk_py.stats.measures.summary

.. autofunction:: orion_finance_sdk_py.stats.measures.product_scoreboard

.. autofunction:: orion_finance_sdk_py.stats.rfr.rfr_decimal

.. automodule:: orion_finance_sdk_py.stats.covariance
   :members:

.. automodule:: orion_finance_sdk_py.stats.panels
   :members:

.. automodule:: orion_finance_sdk_py.stats.factors
   :members:

.. automodule:: orion_finance_sdk_py.stats.portfolio
   :members:
```

## RPC defaults

```{eval-rst}
.. automodule:: orion_finance_sdk_py.rpc
   :members:
   :undoc-members:
```
