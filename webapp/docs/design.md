# Open Co-Scientist Frontend Design

## Sidebar Design Contract

本项目侧边栏采用 Codex-style work queue / project tree，而不是传统 feature menu。侧边栏的职责是帮助研究员回到正在推进的研究项目，并在项目上下文中进入论文、假设、实验、报告和项目 AI。

### Information Architecture

侧边栏默认按以下层级组织：

```text
全局动作
  新建项目
  项目 AI
  任务队列
  资料库
  搜索

置顶
  当前或最近研究项目
    论文
    假设
    实验
    报告
    项目 AI

项目
  其他最近研究项目

专家与运行
  研究工具
  研究产出
  运行准备
```

### Product Principles

- 侧边栏优先展示项目，而不是系统内部模块。
- `论文 / 假设 / 实验 / 报告 / 项目 AI` 是项目下的子工作区，不是默认全局主导航。
- `工具 / agent / worker / execution memory / provider / prompt / raw API` 等能力只进入专家与运行区域，普通研究路径默认隐藏。
- 项目节点应支持展开、收起、当前项高亮和子工作区数量提示。
- 置顶区域优先展示当前路由对应项目，其次展示运行中项目，再展示最近项目。
- 子工作区必须使用稳定高度、截断标题和右侧数量 pill，避免侧边栏因动态内容产生 layout shift。
- 移动端侧边栏保持纵向项目树，可滚动，不切换回功能横向 tab。

### Current Implementation

- Sidebar component: `open-coscientist/webapp/src/components/navigation/PrimaryNav.tsx`
- Shell placement: `open-coscientist/webapp/src/app/layout/AppShell.tsx`
- Shared styles: `open-coscientist/webapp/src/styles/components.css`
- Responsive styles: `open-coscientist/webapp/src/styles/responsive.css`

### Non-goals

- 不把所有页面入口平铺成一组同权重按钮。
- 不在普通研究员路径直接暴露 raw run id、provider key、worker internals、prompt、MCP 或 stack trace。
- 不把 demo/synthetic 结果伪装成真实科学证据。
