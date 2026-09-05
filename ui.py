from __future__ import annotations

import json

import httpx
import streamlit as st


BACKEND = "http://127.0.0.1:8000"


def call(method: str, path: str, **kwargs):
    """
    调用 TestPilot FastAPI 后端。

    Streamlit 运行在 8501，
    真正的 Agent 后端运行在 8000。
    """
    try:
        with httpx.Client(
            timeout=60,
            trust_env=False,
        ) as client:
            response = client.request(
                method,
                f"{BACKEND}{path}",
                **kwargs,
            )
    except httpx.RequestError as exc:
        st.error(
            f"无法连接 TestPilot 后端 {BACKEND}\n\n"
            f"{type(exc).__name__}: {exc}"
        )
        return None

    if response.is_error:
        st.error(
            f"后端错误 {response.status_code}: "
            f"{response.text}"
        )
        return None

    try:
        return response.json()
    except ValueError:
        st.error("后端返回的内容不是合法 JSON")
        return None


# --------------------------------------------------
# 页面基础设置
# --------------------------------------------------

st.set_page_config(
    page_title="TestPilot Lite",
    layout="wide",
)

st.title("TestPilot Lite · 本地 API 智能测试 Agent")

st.caption(
    "只允许测试 localhost / 127.0.0.1，"
    "写操作必须人工确认。"
)


# --------------------------------------------------
# 新建测试会话
# --------------------------------------------------

with st.form("new_session"):
    openapi_url = st.text_input(
        "OpenAPI URL",
        "http://127.0.0.1:8001/openapi.json",
    )

    goal = st.text_area(
        "测试目标",
        "为商品与订单接口生成正常、边界和异常用例，并输出测试报告。",
    )

    max_cases = st.slider(
        "最多生成用例",
        min_value=1,
        max_value=20,
        value=12,
    )

    submitted = st.form_submit_button(
        "分析接口",
        type="primary",
    )


if submitted:
    state = call(
        "POST",
        "/sessions",
        json={
            "openapi_url": openapi_url,
            "goal": goal,
            "max_cases": max_cases,
        },
    )

    if state:
        st.session_state["session_id"] = state["session_id"]
        st.rerun()


# --------------------------------------------------
# 当前 Session
# --------------------------------------------------

session_id = st.session_state.get("session_id")


if session_id:

    session_col, button_col = st.columns([5, 1])

    with session_col:
        st.caption(f"Session ID：`{session_id}`")

    with button_col:
        if st.button(
            "新建会话",
            use_container_width=True,
        ):
            del st.session_state["session_id"]
            st.rerun()


    # --------------------------------------------------
    # 获取完整 AgentState
    # --------------------------------------------------

    state = call(
        "GET",
        f"/sessions/{session_id}",
    )


    if state:

        # --------------------------------------------------
        # 当前状态
        # --------------------------------------------------

        st.subheader(
            f"会话状态：{state['phase']}"
        )

        if state.get("error"):
            st.error(state["error"])


        # --------------------------------------------------
        # 基础指标
        # --------------------------------------------------

        info_col1, info_col2, info_col3 = st.columns(3)

        info_col1.metric(
            "发现接口",
            len(state.get("operations", [])),
        )

        info_col2.metric(
            "生成用例",
            len(state.get("test_cases", [])),
        )

        info_col3.metric(
            "Agent 步数",
            state.get("step_count", 0),
        )


        # --------------------------------------------------
        # Agent 决策轨迹 + 测试用例
        # --------------------------------------------------

        left, right = st.columns(2)


        # 使用昨天新增的 /trace API
        trace = call(
            "GET",
            f"/sessions/{session_id}/trace",
        )

        if trace is None:
            # 即使 trace API 暂时有问题，
            # 仍然可以退回 AgentState 里的 trace
            trace = state.get("trace", [])


        with left:
            st.markdown("### Agent 决策轨迹")

            if trace:
                st.dataframe(
                    trace,
                    use_container_width=True,
                    hide_index=True,
                )
            else:
                st.info("暂时还没有 Agent 决策轨迹。")


        with right:
            st.markdown("### 已生成测试用例")

            test_cases = state.get("test_cases", [])

            if test_cases:
                st.dataframe(
                    test_cases,
                    use_container_width=True,
                    hide_index=True,
                )
            else:
                st.info("暂时还没有生成测试用例。")


        # --------------------------------------------------
        # Human-in-the-loop
        # --------------------------------------------------

        if state["phase"] == "waiting_approval":

            st.warning(
                "检测到 POST / PUT / PATCH / DELETE 写操作。"
                "请检查下面的写操作测试用例后决定是否执行。"
            )


            write_cases = [
                case
                for case in state.get("test_cases", [])
                if case.get("needs_approval")
            ]


            st.markdown("### 待审批写操作")


            for case in write_cases:

                with st.expander(
                    f"{case['method']} {case['path']} "
                    f"· {case['case_id']}"
                ):

                    st.write(
                        "**测试标题：**",
                        case.get("title", ""),
                    )

                    st.write(
                        "**Method：**",
                        case["method"],
                    )

                    st.write(
                        "**Path：**",
                        case["path"],
                    )

                    st.write(
                        "**预期状态码：**",
                        case.get("expected_status"),
                    )


                    if case.get("path_params"):
                        st.write("**Path Params：**")

                        st.code(
                            json.dumps(
                                case["path_params"],
                                ensure_ascii=False,
                                indent=2,
                            ),
                            language="json",
                        )


                    if case.get("query_params"):
                        st.write("**Query Params：**")

                        st.code(
                            json.dumps(
                                case["query_params"],
                                ensure_ascii=False,
                                indent=2,
                            ),
                            language="json",
                        )


                    st.write("**Request Body：**")

                    st.code(
                        json.dumps(
                            case.get("json_body"),
                            ensure_ascii=False,
                            indent=2,
                        ),
                        language="json",
                    )


            approve_col, reject_col = st.columns(2)


            if approve_col.button(
                "批准执行写操作",
                type="primary",
                use_container_width=True,
            ):

                approved_state = call(
                    "POST",
                    f"/sessions/{session_id}/approve",
                    json={
                        "approved": True,
                    },
                )

                if approved_state:
                    st.rerun()


            if reject_col.button(
                "拒绝写操作，只执行安全请求",
                use_container_width=True,
            ):

                rejected_state = call(
                    "POST",
                    f"/sessions/{session_id}/approve",
                    json={
                        "approved": False,
                    },
                )

                if rejected_state:
                    st.rerun()


        # --------------------------------------------------
        # 执行结果
        # --------------------------------------------------

        results = state.get("results", [])


        if results:

            st.markdown("### 执行结果")


            # ------------------------------
            # 统计通过 / 失败 / 拦截
            # ------------------------------

            passed_count = sum(
                1
                for item in results
                if item.get("passed") is True
            )

            blocked_count = sum(
                1
                for item in results
                if item.get("blocked") is True
            )

            failed_count = sum(
                1
                for item in results
                if (
                    item.get("passed") is False
                    and item.get("blocked") is False
                )
            )


            metric_passed, metric_failed, metric_blocked = st.columns(3)


            metric_passed.metric(
                "通过",
                passed_count,
            )

            metric_failed.metric(
                "失败",
                failed_count,
            )

            metric_blocked.metric(
                "安全拦截",
                blocked_count,
            )


            st.dataframe(
                results,
                use_container_width=True,
                hide_index=True,
            )


        # --------------------------------------------------
        # Bug 知识库建议
        # --------------------------------------------------

        bug_advice = state.get("bug_advice", [])


        if bug_advice:

            st.markdown("### 历史 Bug 检索建议")


            for item in bug_advice:

                with st.expander(
                    item["title"]
                ):

                    st.write(
                        "**可能原因：**",
                        item["likely_cause"],
                    )

                    st.write("**建议检查：**")


                    for check in item["checks"]:
                        st.write(f"- {check}")


        # --------------------------------------------------
        # 最终报告
        # --------------------------------------------------

        if state["phase"] == "completed":

            report = call(
                "GET",
                f"/sessions/{session_id}/report",
            )


            if report:

                summary = report["summary"]


                st.markdown("### 测试报告摘要")


                summary_col1, summary_col2, summary_col3, summary_col4 = (
                    st.columns(4)
                )


                summary_col1.metric(
                    "已执行",
                    summary["executed_cases"],
                )

                summary_col2.metric(
                    "通过",
                    summary["passed_cases"],
                )

                summary_col3.metric(
                    "失败",
                    summary["failed_cases"],
                )

                summary_col4.metric(
                    "拦截",
                    summary["blocked_cases"],
                )


                st.success(
                    "测试完成 · "
                    f"通过率：{summary['pass_rate']:.2%} · "
                    f"平均响应时间："
                    f"{summary['average_latency_ms']:.2f} ms"
                )


                st.download_button(
                    "下载 JSON 报告",
                    data=json.dumps(
                        report,
                        ensure_ascii=False,
                        indent=2,
                    ),
                    file_name=(
                        f"testpilot-{session_id}.json"
                    ),
                    mime="application/json",
                    use_container_width=True,
                )
