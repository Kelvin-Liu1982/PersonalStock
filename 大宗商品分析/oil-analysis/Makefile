# 国际原油价格 · 五维度分析仪表盘
#
# 注意：Python 必须 3.13.x（见 requirements.txt 顶部说明），
# 用 3.14 构建会让产物 HTML 无法与既有版本字节复现。
PY ?= python3.13

.PHONY: help setup extract dataset html build all serve clean check check-geo

help:
	@echo "可用目标："
	@echo "  make setup     安装 Python 依赖（pdfplumber / openpyxl）"
	@echo "  make extract   解析 data/raw 下的 PDF/Excel -> data/processed/"
	@echo "  make dataset   抓取线上五维数据 -> data/dataset/"
	@echo "  make html      渲染仪表盘 -> output/crude_oil_dashboard.html"
	@echo "  make build     = dataset + html"
	@echo "  make all       = extract + dataset + html"
	@echo "  make serve     本地预览 http://localhost:8000/"
	@echo "  make clean     删除产物与缓存（不动 data/raw）"

setup:
	$(PY) -m pip install -r requirements.txt

extract dataset html build all:
	$(PY) run.py $@

serve:
	$(PY) run.py serve

clean:
	rm -rf output/
	find . -name __pycache__ -type d -not -path "./tools/node_modules/*" -prune -exec rm -rf {} + 2>/dev/null || true
	@echo "已清理 output/ 与 __pycache__（data/raw 与 data/dataset 保留）"
