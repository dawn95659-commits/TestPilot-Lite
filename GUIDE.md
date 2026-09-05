# TestPilot Lite 逐日实操指南

适用环境：VS Code、Windows、Python 3.11  
实施日期：2026 年 8 月 25 日—9 月 10 日  
前置成果：PaperPilot 已完成 RAG、检索评测、FastAPI、Streamlit 与测试

## 1. 这个项目到底做什么

TestPilot Lite 的用户是初级测试开发、后端开发者或接口负责人。用户给它一个**自己创建的本地 FastAPI 服务**的 `openapi.json`，它会：

1. 读取接口契约；
2. 识别路径、方法、参数、请求体和响应 Schema；
3. 生成正常、边界和异常测试用例；
4. 判断是否包含会修改数据的操作；
5. 在 POST、PUT、PATCH、DELETE 前暂停，等待用户审批；
6. 用 HTTPX 执行获准的请求；
7. 用确定性代码检查状态码、JSON 结构和响应时间；
8. 失败时从历史 Bug 知识库检索排查建议；
9. 保存 Agent 的每一步决策和最终报告。

你通过这个项目回答一个关键面试问题：

> 如何让大模型参与复杂任务，同时不把执行权和安全边界完全交给模型？

答案是：模型或规划器负责“建议下一步”，Pydantic 校验工具决策，Python 工具执行实际操作，Guardrail 限制目标和方法，人类审批写操作，评测集检查 Agent 是否选对工具。

## 2. 它和 PaperPilot 的关系

| PaperPilot 已证明 | TestPilot 新增证明 |
|---|---|
| 文档解析、Chunk、Embedding | OpenAPI 契约解析与 `$ref` 展开 |
| Retriever、Reranker | Planner、Tool Registry、Agent State |
| 引用回答、拒答 | 工具执行、观察结果、循环终止 |
| RAG 评测 | Agent 工具选择与安全评测 |
| FastAPI、Streamlit | 多服务调用与人工审批 |
| Bad Case 分析 | 失败后调用 Bug 知识检索工具 |

PaperPilot 的主路径是“问题 → 检索 → 生成”；TestPilot 的主路径是“目标 → 决策 → 工具 → 观察 → 再决策”。

## 3. 先跑完整工程

### 3.1 VS Code 操作

1. 解压工程并在 VS Code 选择“文件 → 打开文件夹”；
2. 按 `Ctrl+Shift+P`；
3. 选择 `Python: Select Interpreter`；
4. 创建虚拟环境后选择 `.venv\Scripts\python.exe`；
5. 打开“终端 → 新建终端”。

### 3.2 第一次验证

```powershell
py -3.11 -m venv .venv
.venv\Scripts\python.exe -m pip install --upgrade pip
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe -m pytest
.venv\Scripts\python.exe -m evaluation.run_eval
.venv\Scripts\python.exe -m scripts.e2e_check
```

验收：

- 测试输出 `34 passed`；
- 评测输出 `tool_selection_accuracy: 1.0`；
- 端到端输出 `E2E PASS`；
- `data/reports/` 出现 JSON 和 Markdown 报告。

如果失败，按顺序检查：VS Code 解释器、当前终端目录、8000/8001 端口占用、依赖是否装进 `.venv`。

## 4. 8 月 25 日—9 月 10 日安排

每天建议 3—4 小时：45 分钟阅读、2 小时代码、45 分钟测试、30 分钟日志与复述。代码已经给你，但学习时必须先根据当天目标自己写或遮住答案重写关键函数，再和参考实现比较。

### 8 月 25 日：理解产品与跑通基线

阅读：`README.md`、`sample_api/main.py`、FastAPI First Steps。  
实操：运行 `pytest`、`evaluation.run_eval`、`scripts.e2e_check`。打开两个 `/docs` 页面，手动调用一次 `GET /products`。  
修改：在样例 API 新增一个价格不低于 0 的 Pydantic 约束。  
输出：`docs/day01_baseline.md`，记录环境、三条命令输出和一张 Swagger 截图。  
验收：能解释为什么一个项目中有 8000 和 8001 两个服务。

### 8 月 26 日：HTTP 与 OpenAPI

阅读：OpenAPI `Paths Object`、`Operation Object`、`Parameter Object`；`sample_api/main.py`。  
实操：访问 `http://127.0.0.1:8001/openapi.json`，找到 `paths`、`operationId`、`requestBody`、`responses` 和 `components/schemas`。  
修改：给样例 API 增加 `GET /products?max_price=...` 查询参数；观察 OpenAPI 的变化。  
输出：`docs/openapi_notes.md`，用自己的话解释五个字段。  
验收：不看资料指出 path parameter、query parameter 和 request body 的区别。

### 8 月 27 日：自己实现 OpenAPI 解析器

阅读：`testpilot/openapi_parser.py`、`tests/test_openapi_parser.py`。  
实操：先只写一个函数打印 `method + path + operationId`，再逐步补参数、请求体和响应。  
命令：

```powershell
.venv\Scripts\python.exe -m pytest tests\test_openapi_parser.py -q
```

修改：让解析器忽略不认识的非 HTTP 字段。  
输出：一张解析结果截图。  
验收：解释 `$ref` 为什么存在、为什么要防止递归引用。

### 8 月 28 日：Schema 驱动的用例生成

阅读：`testpilot/case_generator.py`、JSON Schema 的 `type`、`properties`、`required`、`minimum`、`enum`。  
实操：遮住参考实现，重写 `_build_example()`；分别为 GET 列表、GET 单条、POST 创建生成用例。  
命令：

```powershell
.venv\Scripts\python.exe -m pytest tests\test_case_generator.py -q
```

修改：给字符串 `minLength` 增加一个边界用例，或给数值 `minimum` 增加一个低于下界的异常用例。  
输出：至少 6 条用例的 JSON。  
验收：能解释为什么“LLM 生成用例”仍必须经过 Pydantic 和数量限制。

### 8 月 29 日：安全执行器

阅读：`security.py`、`http_client.py`、HTTPX timeout 与 redirects。  
实操：依次把目标改成外部域名、错误端口、HTTPS、本地正确 URL，观察哪个阶段被拦截。  
命令：

```powershell
.venv\Scripts\python.exe -m pytest tests\test_security.py -q
```

修改：在 `.env` 中把允许端口改为 `8001,8011`，重新验证。  
输出：`docs/security_policy.md`。  
验收：说出至少 6 条 Guardrail，并解释为什么 `follow_redirects=False`。

### 8 月 30 日：响应校验

阅读：`validators.py`、`tests/test_validation_and_search.py`。  
实操：故意让样例接口把 `price` 从数字改为字符串；执行测试并查看 Schema mismatch；修复后回归。  
命令：

```powershell
.venv\Scripts\python.exe -m pytest tests\test_validation_and_search.py -q
```

输出：一份“故障注入前—失败—修复后”的记录。  
验收：能区分 HTTP 状态码正确与响应结构正确。

### 8 月 31 日：Agent State、Planner 与 Tool

阅读：`models.py` 中的 `AgentState/Phase/ToolDecision`，以及 `planner.py`。  
实操：在纸上或 Mermaid 画出七个 phase；逐个调用 `HeuristicPlanner.decide()`。  
修改：给 TraceEvent 增加一个可选 `duration_ms` 字段，保持测试通过。  
输出：`docs/agent_state.md`。  
验收：能说明 Agent、固定工作流和普通函数链的相同点与不同点。

### 9 月 1 日：实现 Agent 循环

阅读：`controller.py` 的 `run()` 和工具注册表。  
实操：先写只支持 3 个工具的循环，再恢复完整 6 工具版本；在每步加断点，查看 `state.phase` 如何改变。  
命令：

```powershell
.venv\Scripts\python.exe -m pytest tests\test_controller_and_api.py -q
```

修改：把最大步数暂时改为 1，确认 Agent 进入 FAILED；改回 10。  
输出：一段 1 分钟屏幕录制，展示断点中的状态变化。  
验收：闭卷写出“决策 → 工具 → 观察 → 更新状态 → 再决策”的伪代码。

### 9 月 2 日：Human-in-the-loop

阅读：`controller.approve()`、`security.requires_approval()`、UI 审批按钮。  
实操：分别批准和拒绝写操作，对比报告中的 executed、blocked 和 pass_rate。  
修改：在审批页面额外显示所有写操作的 method、path、body。  
输出：批准版和拒绝版两份报告。  
验收：解释为什么拒绝写操作不是系统故障，以及报告应该如何统计 blocked。

### 9 月 3 日：TestPilot 后端 API 与持久化

阅读：`api.py`、`store.py`、FastAPI request body / error handling / testing。  
实操：在 Swagger 中依次调用 `POST /sessions`、`GET /sessions/{id}`、`POST /approve`、`GET /report`。  
修改：增加 `GET /sessions/{id}/trace`，只返回轨迹。  
输出：接口清单和状态码表。  
验收：解释 201、404、409、422 分别在什么情况下出现。

201 Created:POST /sessions 成功创建 Agent session
200 OK:读取 session / approve / report / trace 成功
404 Not Found:session_id 不存在
409 Conflict:session 存在，但当前 phase 不允许操作。例如：completed 后再次 approve
422 Unprocessable Entity：请求体格式能解析，但字段校验失败例如：goal 长度 < 3  max_cases < 1 或 > 20


### 9 月 4 日：Streamlit 前端联调

阅读：`ui.py`、Streamlit `st.form`、`st.session_state`、`st.dataframe`、`st.download_button`。  
实操：启动三个终端，完成创建会话、审批、查看结果、下载报告。  
修改：增加通过/失败/拦截三个指标卡。  
输出：至少 4 张页面截图。  
验收：能画出“浏览器 → TestPilot API → Sample API”的请求路径。

### 9 月 5 日：把 PaperPilot 的 RAG 思路迁移过来

阅读：`bug_search.py`、`data/bug_knowledge.json`。  
实操：故意制造状态码或 Schema 失败，确认只有失败后才调用 `search_bug_knowledge`。  
修改：新增 3 条来自你本人 PaperPilot 调试经历的 Bug 条目；不得包含密钥或隐私。  
输出：失败用例到检索建议的映射表。  
验收：解释这个轻量检索与 PaperPilot Embedding 检索的差别，以及何时值得换成向量检索。

### 9 月 6 日：自动化测试与 Mock

阅读：`tests/conftest.py`、`httpx.MockTransport`、FastAPI TestClient。  
实操：逐个运行四组测试，阅读 fixture 如何模拟 OpenAPI 和业务响应。  
修改：增加至少 5 项测试：超时、非 JSON、OpenAPI 超过限制、未知 session、未审批继续。  
命令：

```powershell
.venv\Scripts\python.exe -m pytest --cov=testpilot --cov-report=term-missing
```

输出：覆盖率报告。  
验收：项目测试总数达到至少 39，并解释为什么自动化测试不能真实调用付费模型。

### 9 月 7 日：Agent 评测与 Bad Case

阅读：`evaluation/agent_cases.csv`、`evaluation/run_eval.py`。  
实操：把评测扩展为 30 条，至少覆盖工具选择、参数合法、任务完成、安全拦截、步数。  
建议字段：

```text
id,user_goal,phase,expected_tool,actual_tool,arguments_valid,task_completed,safety_pass,step_count,notes
```

修改：故意让一条规则选错工具，保存优化前结果；修复后再运行并保存优化后结果。  
输出：`evaluation/bad_cases.md`。  
验收：至少分析 3 类 Bad Case，安全拦截率必须是 100%。到这一天可发布 MVP 并开始投递。

### 9 月 8 日：可选 LLM 规划器

前提：前 14 天任务无欠账。否则跳过。  
阅读：`CompatibleLLMPlanner` 与模型提供方当前的结构化输出/函数调用文档。  
实操：复制 `.env.example` 为 `.env`，配置你 PaperPilot 已验证过的兼容接口，设置 `TESTPILOT_PLANNER=llm`。  
注意：LLM 只看到状态摘要，不直接看到密钥，不执行 HTTP，不得绕过 `security.py`。  
输出：heuristic 与 LLM 的工具选择率、平均步骤数、非法 JSON 次数对比。  
验收：能说明“模型负责规划”和“代码负责执行”的责任边界。

### 9 月 9 日：求职包装

完成：

- README 的真实指标；
- 架构图和状态图；
- 3—5 分钟演示视频；
- 一份测试报告；
- 一份 Agent 评测报告；
- 3 个 Bad Case；
- 4—6 张项目截图；
- AI 应用、Python 后端、AI 测试三版项目描述。

演示顺序：正常创建 → 展示用例 → 写操作审批 → 执行 → 故障注入 → Bug 检索 → 下载报告。

### 9 月 10 日：新环境复现与冻结

1. 复制工程到一个新目录；
2. 不复制 `.venv`、`.env`、sessions 和 reports；
3. 只按 README 从零安装；
4. 运行测试、评测和 E2E；
5. 修复所有说明缺口；
6. Git 标记 `v0.1.0`；
7. 正式集中投递。

最终验收：新目录中仅靠 README，30 分钟内能启动并演示；你能闭卷画架构、讲状态流转、解释审批与安全，并讲清 3 个真实 Bad Case。

## 5. 推荐学习资料：只看与当天任务相关的章节

| 主题 | 资料 | 重点 |
|---|---|---|
| FastAPI 基础 | <https://fastapi.tiangolo.com/tutorial/> | First Steps、Request Body、Handling Errors、Testing |
| OpenAPI | <https://spec.openapis.org/oas/latest.html> | Paths、Operation、Parameter、Request Body、Responses、Schema |
| Pydantic | <https://docs.pydantic.dev/latest/concepts/models/> | BaseModel、Field、validation、model_dump |
| HTTPX | <https://www.python-httpx.org/quickstart/> | request、timeout、exceptions |
| HTTPX Transport | <https://www.python-httpx.org/advanced/transports/> | MockTransport 与测试替身 |
| JSON Schema | <https://json-schema.org/understanding-json-schema/> | object、array、required、type、additionalProperties |
| pytest | <https://docs.pytest.org/en/stable/getting-started.html> | fixture、parametrize、raises |
| Streamlit | <https://docs.streamlit.io/develop/api-reference> | form、session_state、dataframe、download_button |
| Function Calling | <https://platform.openai.com/docs/guides/function-calling> | 工具 Schema、模型选择、应用执行、返回观察结果 |

阅读纪律：遇到接口版本差异，以官方当前文档和项目测试为准；不要为了“看完教程”推迟编码。

## 6. 最容易犯的错误

1. 把一次模型 JSON 输出称为 Agent，却没有状态、工具、观察和循环；
2. 让 LLM 自己决定请求是否通过，导致结果不可复现；
3. 允许任意 URL，变成有安全风险的未授权测试器；
4. 写操作没有 Human-in-the-loop；
5. 自动化测试真实调用模型，导致慢、贵、不稳定；
6. 只展示成功 Demo，没有 Agent 评测和 Bad Case；
7. 一开始加入 LangGraph、Dify、React、Docker，导致主链路没完成。

## 7. 到 9 月 7 日与 9 月 10 日分别应达到什么程度

9 月 7 日 MVP：

- 自动读取本地 OpenAPI；
- 至少 4 个业务 operation；
- 生成至少 8 条测试用例；
- 至少 5 个 Agent 工具；
- 写操作审批；
- 状态码和 Schema 校验；
- Bug 检索；
- FastAPI + Streamlit；
- 至少 39 项测试、30 条 Agent 评测；
- 3 类 Bad Case。

9 月 10 日求职版：

- 新环境复现成功；
- README 数字与结果文件一致；
- 架构图、报告、截图、演示视频齐全；
- 能在 3 分钟内讲清问题、方案、权衡、安全和指标；
- Git 冻结 `v0.1.0`；
- 开始使用岗位定制版简历投递。

## 8. 面试时的三分钟讲法

第一段：我做了一个只面向本地自建 API 的智能测试 Agent，它从 OpenAPI 自动理解接口并生成测试用例。  
第二段：系统采用 Planner—Tool—State 循环；LLM 或确定性规划器只选择工具，HTTP 执行和结果校验由 Python 完成。  
第三段：我加入了本地主机/端口白名单、超时、最大步数、用例上限和写操作人工审批，避免 Agent 越权。  
第四段：我通过自动化测试、工具选择评测、安全拦截率和 Bad Case 分析证明它可复现，并保存优化前后真实指标。

真正讲述时，把测试数、通过率、覆盖率、评测数、Bad Case 数替换成你最终亲自复现的数字。

