# -*- coding: utf-8 -*-
"""原油看板代码包。

分层约定：
    src/common/    公共工具（HTTP、序列运算）
    src/fetch/     按五维度组织的抓取模块（供给侧/需求侧/地缘/宏观/突发）
    src/score/     维度打分模型
    src/pipeline/  编排与渲染
"""
