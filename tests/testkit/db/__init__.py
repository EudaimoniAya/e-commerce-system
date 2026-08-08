"""tests/testkit/db — 使用与 override 相同 AsyncSession 的 DB 状态断言 helper。

只读 Repository + 同一 ``db_session``。
禁止 Case import ``app.*.repository``；禁止为 Assert 调 service。
"""
