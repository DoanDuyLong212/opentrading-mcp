# 04 — Phạm vi và Feature List (L07-L08)

## L07 — Agents Overreach and Under-Finish

**Bệnh:** bảo `add auth`, agent sửa schema+routes+frontend+tiện refactor middleware. 2h sau 12 files 800 dòng, không feature nào e2e. Xung lực `do a little extra`.

Không phải lỗi model, lỗi harness: prompt rộng không boundary → `start multiple` thay vì `finish one`.

**Toán:** budget reasoning `C`, kích `k` task song song mỗi task `C/k`. `C/k` dưới ngưỡng tối thiểu → không việc nào xong. Ví dụ registration bung 6 bước (model→route→mail→bcrypt→refactor middleware→reorg tests), dở dang, coupling, session sau bó tay. Anthropic: `small next step` ~ WIP=1 completion +37%, lines sinh ra tương quan âm với completion — viết càng nhiều xong càng ít.

**Thuật ngữ:**
- Overreach: kích quá nhiều/session. 5 features 0 pass e2e là overreach.
- Under-finish: `passed/activated` thấp. Code viết test không pass là under-finish.
- Cộng hưởng: overreach pha loãng attention → under-finish → code dở tăng complexity → overreach tiếp.
- Little `L=lambda*W`: WIP cao → lead time dài → fail tăng. Human có trực giác đủ rồi, agent `let me fix this too` tốn vài tokens nhưng pha loãng toàn bộ.

**Workflow WIP=1:**
```
Queue -> Pick exactly one -> Only one active -> e2e verify -> pass Commit+unlock next, fail quay Active
C/1 -> One passing thắng C/5 -> Five partials (low VCR, high rework)
```

**4 cách đúng:**
1. Enforce trong AGENTS: `One at a time`, `Only next after current e2e pass`, `Don't refactor B while A`.
2. Evidence显式: done = `curl POST /api/register | jq .status==201`, pytest pass, không phải looks fine.
3. Externalize scope DAG: node=work unit, edge=dependency, state `not_started/active/blocked/passing`. Session mới đọc biết active nào, done chuẩn nào.
4. Monitor VCR = `verified/activated`. VCR<1.0 block task mới, tạo completion pressure.

Code: `scope-surface-example.md` (Bad `Implement indexing` vs Better 5 steps parse/chunk/persist/UI/reindex), `scope-tracker.ts` (F-001 active nhưng changelog drift F-002/F-003/F-004 → DRIFT), `next-task-template.md`.

Case REST 8 features: unconstrained S1 kích 5, 800 dòng/12 files, pass 20%, S3 xong 3/8. WIP=1 S1 chỉ registration 200 dòng/4 files pass 100%, S4 xong 7/8, code ít hơn completion 87.5% vs 37.5%.

## L08 — Feature Lists Are Harness Primitives

**Lật nhận thức:** không phải memo chống quên, mà primitive — scheduler/verifier/handoff/tracker đều dựa vào, không bypass được (như DB trigger vs app check). Không có nó, các component không consensus. Hỏi làm e-commerce, agent báo done nhưng checkout bấm không gì, payment chưa nối, vì chưa thống nhất done là gì. Memo `auth done, cart mostly, need payments` → session mới mất 20p, thậm chí re-implement. Progress tốt -60-80% diagnose time.

**Mỗi item = (behavior, verification, state):** làm gì, thế nào là xong, đang ở đâu. Thiếu 1 là incomplete.
```
feature_list.json -> Scheduler picks not_started -> Agent one -> Verifier runs -> pass Mark passing+evidence, fail Keep active, dep issue Blocked -> Handoff update
```
Single source of truth + back-pressure: chưa pass là áp lực, zero là xong.

**Schema chuẩn:**
```json
{"id":"F03","behavior":"POST /cart/items returns 201","verification":"curl -X POST ... | jq .status==201","state":"passing","evidence":"commit abc123, test log"}
```
Thực tế thêm `layers/category`: `qna-001 grounded_qa description ... verification[] passes bool`. Validator `feature-list-validator.ts`: bắt `id/category/description`, `verification array`, `passes bool`, flag `passes without evidence`. `pass-gate-policy.md`: chỉ `false→true` khi workflow exercised + evidence + no blocking + app not broken. Tương đương `verify-feature.sh` tự update, agent không tự sửa state. Rule: `Only one active`, `Must pass before passing`, `Don't modify states yourself`.

**Granularity 1 session/feature:** phải completable trong 1 session. `Add items to cart` tốt, `Implement cart` quá rộng, `Create name field` quá hẹp overhead. State machine `not_started→active→passing` (nhánh blocked), chỉ tiến khi verify pass, không quay lại.

Case 10 features: memo 3 sessions `auth/list done, cart mostly bugs` → 20p + rework; structured đọc 3p biết F01-05 passing F06 active F07-10 not_started, pick F06 không trùng, completion +45%, duplicate zero.
