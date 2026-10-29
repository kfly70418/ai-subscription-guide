# GPT / Claude 账号代充比价导航

网站：https://kfly70418.github.io/ai-subscription-guide/
价格来源：https://daichongbijia.com/chatgpt/ 和 https://daichongbijia.com/claude/

## 日常更新

安装依赖：`python -m pip install -r requirements.txt`。
执行 `python update_prices.py --publish`：读取 GitHub main 最新页面与报价、采集来源、验证、更新数据、单次提交并检查 Pages 公网页面与数据一致。首次发布应用修改使用 `--publish --include-site`；日常任务不要使用 `--include-site`，避免覆盖远端样式和脚本修改。

定时任务：Codex 本聊天的每日 09:00（Asia/Shanghai）任务。任务依赖本机与 Codex 可运行、网络正常，以及 Git Credential Manager 中 kfly70418 的有效 GitHub 登录。它不是 GitHub Actions 云端定时任务。

## 数据与口径

- `data/prices.json`：最近成功采集的报价。
- `data/history/YYYY-MM-DD.json`：每日快照，同日重复运行更新同一快照。
- 每条保留商家、套餐、CNY 来源标价、交付方式、来源报价日期、限制说明和来源链接。
- 采集日期不替代报价日期；不复制来源站评分、不声称独立核验或全网最低价。
- 来源明确标历史，或报价日期距当天超过 14 天，均标历史；默认只展示近期。
- 按产品、套餐、周期和币种分组排序；周期未注明组只列标价，不推算月费。
- 页面直接包含报价正文，也支持浏览器搜索、产品与套餐筛选、查看历史。
- 只抓取允许访问的公开列表，不抓取 robots 禁止的 /go/ 跳转。

## 失败保护

两个来源都成功解析才写快照。价格字段不一致、日期异常、空列表、同类条数减少超过 40%、同一报价突变超过 60%时停止，需人工检查。新价格永不猜测或填零。页面超过 36 小时未采集会显示陈旧提醒。发布通过 GitHub API 非强制更新 main；远端同时有新提交则停止，重跑会从新版本开始。公网部署未验证成功不会标为发布成功。

日常提交仅包含 index.html、当前数据和当日历史快照。GitHub 凭据只从环境变量或系统 Git Credential Manager 临时读取，不输出、不保存、不提交。

测试：`python -m unittest test_update_prices.py`；仅检查公网已发布内容：`python update_prices.py --verify-only`。
