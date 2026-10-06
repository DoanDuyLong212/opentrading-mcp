# 08 — Graph Engineering (L14): Vẽ system显式

**Bối cảnh:** joke 18/07/2026 Steinberger moved to graphs + Husain Loop Is Dead — đùa mà thật: graph là cái loop thành khi task đủ phức tạp. Tiền thân nghiêm túc Josh Simmons 04/07.

**4 tầng stack (Rohit):** Prompt (nói làm gì) → Context (cần biết gì) → Loop (iterate đến goal: observe/reason/act/inspect/update/stop) → Graph (nhiều agents/loops/tools/evaluators phối hợp: nodes/edges/state/routing). Stack không thay: node nào cũng prompt+context+tools+memory+loop riêng, graph nối chúng. Harness là foundation dưới tất cả.

## Mổ graph 4 parts

1. Node: đơn vị việc — deterministic code (test/coverage/commit), model call, tool, hoặc full agent có loop+retry. Node là agent mới là ranh giới graph vs workflow.
2. Edge: handoff — parallelism (A fork B+C), conditional (pass trái/fail phải), failure/retry (về chính nó), rollback (verify fail về implement cách 3 hops, thiếu info về research).
3. Shared State: gói chung requirements/notes/code/results, nodes đọc/ghi cùng workspace, phải merge rule (overwrite/append/sum concurrent).
4. Routing: control flow thô: pass→ship, fail→implement, thiếu info→research.
Ví dụ: Shared State – Research(agent) –plan→ Implement –code→ Verify –failed→ Implement, –passed→ Merge –update→ State, Implement –not enough→ Research. So với loop L13 (discover/dispatch/verify/persist), graph phân rã vòng thành显式, rollback ẩn thành hiện.

## Khi nào loop không đủ

Single loop một đường, mọi quyết định một window → 4 câu hỏi: division of labor (ai trước sau), parallelism (đâu song song), rollback (fail về đâu), handoff (reviewer cãi implementer ai thắng, state chung đâu). Catacora: Loops forgive, Graphs force admit workflow not modeled. Loop=deferred rẻ failure vô hình, graph=up-front tốn khai báo đổi readable/auditable/local repair. Loop giấu problem, graph đặt lên giấy. Loop hợp exploration, graph hợp production.

**3 structural failures single loop (eigent.ai):** checker+producer chung não không cứu được.
1. Goodhart: optimize 1 metric → detached: support optimize resolution bằng deflect/đóng bừa, churn x2.
2. Blindness upward: không hỏi goal đúng không — thermostat không hỏi 68°F đúng, sales không hỏi quota sane.
3. Conflict: nhiều loop giằng — speed vs thorough, growth vs quality, dashboard xanh hệ thống thrash.
Graph trả: loop nào feed nào, ai sở hữu target, ai veto/rollback, metric nào move/frozen. Anchors ghim reality: business outcome, ground-truth dataset, human spot-check — dễ skip nhất không được skip.

## Graph vs Workflow + Tax

Cùng skeleton nodes+edges+state+routing (Airflow/Prefect/Temporal, 5 patterns Anthropic 12/2024 đều graphs). Khác node: workflow node=deterministic + edge hardcoded if/switch, graph node=full agent + edge dynamic bởi model/verify. Graph là generalization, workflow là special fully-deterministic. iii.dev: shape dễ disposable, load-bearing là replayability/observability/recoverability. Orchestration Tax (Osmani 05/2026): start rẻ 1 keystroke, close đắt — bạn là GIL của agents, judgment serial không parallelize, thêm nodes tối ưu chỗ không bottleneck là waste. Cảnh báo fake +18%/-85% từ paper P&ID hóa chất khác baseline, không có chữ graph engineering.

## 6-step build + khi nào cần

B1 shared state (tách graph shared vs node private) + merge rule. B2 list nodes hoàn chỉnh (research/implement/verify/merge), verify fresh context không kế thừa implementer. B3 spine deterministic research→implement→verify→merge→end. B4 routing bảng pass→merge/fail→implement. B5 checkpoint every step + pause_before merge chờ human approval. B6 run với thread id.
Cần khi ≥3/5: decomposable độc lập, branch/rollback đáng显式, intermediate đáng save/resume, verifiable per node, benefit>cost. 20-step linear không cần, 5 nodes rollback+parallel+approval thì cần.

## Map MCP-server

`graph.md` mermaid+tables: State (requirements/preset outputs) – Research (scan feed) –plan→ Implement (tool quant) –code→ Verify (pytest/e2e MCP) –failed→ Implement, –passed→ Merge, thiếu info→ Research. Fan-out: 1 node split 5 presets song song worktree riêng, fan-in merge standard. Human node trước `render deploy` có timeout/auto-reject + interrupt format. Chạy ≥2 passes so approval vs verify. Metrics visibility/localization/coordination/observability/reliability.
