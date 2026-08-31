"""离线 RAGAS 评测工作区（ai-ragas-eval）。

- ``golden/``：黄金测试集（``manifest.yaml`` + ``samples.jsonl``），与语料快照同版本；
- ``seed_eval_shop.py``：独立 Eval 店种子脚本（经 catalog.service 写 MySQL、reindex 写 PG）。

仅离线工具，不参与 ``task ci``（golden 文件由 §1.1–1.3 测试校验）。
"""
