#!/usr/bin/env bash
# latest:report — 在浏览器中打开最近生成的 Allure 报告

# -e（errexit） 命令执行失败时退出
# -u（nounset） 未定义变量时报错
# -o pipefail 管道命令失败时报错
set -euo pipefail   

REPORT_DIR="reports/allure-report"

if [ ! -d "$REPORT_DIR" ]; then
    echo "错误：未找到 Allure 报告目录 '$REPORT_DIR'。"
    echo "请先运行 task test:reports 生成报告。"
    exit 1
fi

if ! command -v allure &> /dev/null; then
    echo "错误：未检测到 Allure CLI。"
    echo "安装方法：https://allurereport.org/docs/install/"
    exit 1
fi

allure open "$REPORT_DIR"
