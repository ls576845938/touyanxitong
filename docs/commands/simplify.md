# /simplify — 简化代码与结构

## 用途

用于低风险简化已有代码、文档、架构、组件和重复逻辑。

## 适用场景

- 某个文件超过 500 行，职责不清晰
- 多个函数做几乎相同的事
- 组件嵌套超过 4 层
- 变量命名晦涩
- AI 之前生成的代码过于绕弯
- 文档过于啰嗦

## 示例

```
/simplify src/app/dashboard/page.tsx
/simplify backend/app/engines/thesis_engine.py
/simplify docs/research_closed_loop_mvp.md
```

## 执行流程

1. 读取目标文件
2. 分析复杂度来源
3. 输出简化计划（等待确认）
4. 执行低风险简化
5. 运行已有测试
6. 输出变更报告

## 限制

- 不改变公开 API
- 不破坏业务逻辑
- 不删除未确认的功能
- 不引入新依赖

## 风险等级

中等 — 会修改代码，但保持外部接口不变。

## 相关的 Git 分支建议

在 `alpha-radar-simplify-<target>` 分支上操作。
