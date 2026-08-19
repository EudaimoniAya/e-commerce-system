"""ai 域 retrieval：pgvector 暴力 top-K 检索（强制 shop ACL 过滤）。

MVP 无 ANN 索引（design D9）；SQL 层 ``WHERE shop_id`` 保证店铺隔离（design D10 / ADR-007）。
"""
