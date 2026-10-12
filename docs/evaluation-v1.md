# 第一版评测与验证口径

## 已验证的工程行为

后端测试覆盖鉴权、CSRF、账号隔离、真实 LangGraph 工具调用、真实 Chroma 入库、文档版本切换和周报 CRUD。测试使用确定性模型与 embedding；PostgreSQL checkpoint 测试实际连接专用 PostgreSQL 16。浏览器使用真实 Chromium、HTTP、业务数据库和 Chroma，模型替身仅用来避免费用和模型措辞随机性。

## 已修复的失败案例

1. 导入向量库时立即构建 embedding，导致无网络时 API 无法收集测试。改为按需构建，增加 import 边界测试。
2. 评测题共用默认 thread，且用另一次检索代替工具实际证据。现在每题独立 UUID，通过共享的请求级列表收集实际检索结果；子任务修改列表，而不是依赖 ContextVar 赋值向父任务回传。
3. 混合检索以正文为键，相同正文的不同块被合并。新版优先使用稳定 chunk ID。
4. aiosqlite 0.22 与 checkpoint 2.x API 不兼容。重启测试复现后锁定 0.21。
5. SSE 队列已满时客户端断开，生产者在 finally 中继续等待写入结束标记。改为仅正常结束或已处理错误时写入标记，取消直接释放任务。

## 真实模型评测

**本次未执行真实付费模型评测；回答正确率、真实模型 TTFT、成本和吞吐均为未实测。** 不读取或打印本地真实 Key。现有 `eval/report_hybrid.md` 等是原版静态语料实验，不能代表新版动态知识库质量。

`eval/test_set.jsonl` 是新增独立 30 题：同义改写 8、数字细节 6、跨文档 6、无答案 5、权限拒绝 5。标注参考答案、证据片段和原始文档 SHA256，运行前核验文档版本。没有按此集合调参。数据库中的版本 UUID 属于每次部署，不能直接复用另一环境的 UUID。

```powershell
python -m eval.run_eval --dataset eval/test_set.jsonl --retriever hybrid --mode all --pipeline agent --tag v1-heldout
```

此 CLI 验证保留的静态 Python Agent 链路，需先使用原版入库命令准备静态语料。新版 HTTP 的动态版本、权限、取消另由 API/浏览器测试验证；不能把静态 CLI 结果称为新版线上端到端指标。

`answer_correctness` 对比参考答案；faithfulness 检查实际上下文支持；relevancy 检查是否回应问题；refusal 检查应拒绝的题。来源 Hit@k、MRR、Precision@k 均以文件来源计分，**不是分块正确率或回答准确率**。裁判解析/调用失败记为 null，不把未知当成零；报告需一起统计失败数量。权限安全以工具和资源授权断言为准，模型说“拒绝”本身不构成安全证据。

聊天运行记录 `ttft_ms`、`total_ms` 和可获得的 `usage`。这些是当前应用处理时间与 SDK 元数据，不等于用户网络延迟；SDK 未报告 token 时保存未知。若后续做性能评测，分别记录模型/embedding 冷启动和缓存后的热启动、硬件、并发和样本数。
