---
name: 微信造物台
description: 面向微信生态内容团队的内部生产工作台
colors:
  primary: "oklch(0.563 0.223 11)"
  primary-deep: "oklch(0.44 0.18 11)"
  accent: "oklch(0.36 0.12 230)"
  background: "oklch(1 0 0)"
  surface: "oklch(0.965 0.006 230)"
  ink: "oklch(0.20 0.018 230)"
  muted: "oklch(0.48 0.018 230)"
  border: "oklch(0.88 0.01 230)"
  success: "oklch(0.52 0.13 155)"
  warning: "oklch(0.68 0.15 72)"
  danger: "oklch(0.54 0.20 25)"
typography:
  headline:
    fontFamily: "Inter, PingFang SC, Microsoft YaHei, system-ui, sans-serif"
    fontSize: "1.75rem"
    fontWeight: 700
    lineHeight: 1.25
  title:
    fontFamily: "Inter, PingFang SC, Microsoft YaHei, system-ui, sans-serif"
    fontSize: "1rem"
    fontWeight: 650
    lineHeight: 1.4
  body:
    fontFamily: "Inter, PingFang SC, Microsoft YaHei, system-ui, sans-serif"
    fontSize: "0.9375rem"
    fontWeight: 400
    lineHeight: 1.6
  label:
    fontFamily: "Inter, PingFang SC, Microsoft YaHei, system-ui, sans-serif"
    fontSize: "0.8125rem"
    fontWeight: 600
    lineHeight: 1.4
rounded:
  sm: "6px"
  md: "10px"
  lg: "14px"
spacing:
  xs: "4px"
  sm: "8px"
  md: "16px"
  lg: "24px"
  xl: "32px"
components:
  button-primary:
    backgroundColor: "{colors.primary}"
    textColor: "{colors.background}"
    rounded: "{rounded.sm}"
    padding: "10px 16px"
  input:
    backgroundColor: "{colors.background}"
    textColor: "{colors.ink}"
    rounded: "{rounded.sm}"
    padding: "10px 12px"
---

# Design System: 微信造物台

## Overview

**Creative North Star: "制作台上的红色校样笔"**

这是一套在明亮工作室中长时间使用的生产工具。白色主背景降低视觉疲劳，冷灰结构层分隔导航与工作区，克制的红色只出现在当前选择、关键动作和需要立即处理的校样问题上。作品本身永远是页面里色彩最丰富的对象。

界面拒绝泛化的 AI SaaS 营销感，也不伪装成设计软件。它使用用户熟悉的表格、筛选器、状态标签和分栏检查台，让操作行为可预测。

**Key Characteristics:**

- 高密度但有清晰分组
- 作品预览优先于装饰
- 红色用于动作与校样，不用于铺满界面
- 150–220ms 的状态反馈，减少动效时立即完成

## Colors

纯白与冷灰构成安静工作面，校样红负责关键动作，深蓝灰负责信息结构。

### Primary

- **校样红**：主操作、当前导航、需要立即确认的审核标记。

### Secondary

- **墨蓝灰**：链接、信息标签和辅助强调，不与主操作竞争。

### Neutral

- **工作台白**：页面背景和主要编辑面。
- **器材冷灰**：侧栏、工具条、空状态和次级区域。
- **深墨**：正文和标题。

**The Red Pen Rule.** 校样红在任一屏幕上不超过约 10%，它的稀缺性负责传达优先级。

## Typography

**Display Font:** Inter（中文回退 PingFang SC / Microsoft YaHei）
**Body Font:** Inter（中文回退 PingFang SC / Microsoft YaHei）

**Character:** 单一无衬线字体承载界面、数据和中文长文案，避免作品审阅场景里的字体噪音。

### Hierarchy

- **Headline**（700，1.75rem，1.25）：页面标题和关键工作对象。
- **Title**（650，1rem，1.4）：面板、表格和编辑区标题。
- **Body**（400，0.9375rem，1.6）：说明与主要内容，长文限制在 72ch。
- **Label**（600，0.8125rem，1.4）：字段、状态和紧凑操作。

**The Plain Language Rule.** 状态必须写出业务含义，不用“处理中”掩盖当前阶段。

## Elevation

系统默认扁平，通过背景层级、分隔线和粘性工具条表达深度。阴影只用于浮层、下拉菜单和拖拽中的素材，静态卡片不得同时使用边框和宽模糊阴影。

**The Flat Workbench Rule.** 静止表面没有装饰性阴影；只有真正浮在其他内容上的组件才能获得阴影。

## Components

### Buttons

- **Shape:** 轻微圆角（6px）。
- **Primary:** 校样红底、白字、10px × 16px 内边距。
- **Hover / Focus:** 加深背景；焦点使用 2px 外圈，不通过位移动画表达。
- **Secondary:** 白底深墨字和单像素冷灰边框。

### Chips

- **Style:** 浅色背景和对应深色文字；不得只靠颜色区分成功、警告和失败。
- **State:** 当前筛选同时使用底色、字重和勾选符号。

### Cards / Containers

- **Corner Style:** 普通容器 10px，作品预览 14px。
- **Background:** 白色或器材冷灰。
- **Shadow Strategy:** 默认无阴影。
- **Border:** 仅在同色背景需要结构分隔时使用 1px。
- **Internal Padding:** 16–24px。

### Inputs / Fields

- **Style:** 白底、6px 圆角、1px 冷灰边框。
- **Focus:** 校样红焦点环，不改变控件尺寸。
- **Error / Disabled:** 错误包含文字说明；禁用态保持可读对比度。

### Navigation

桌面端使用窄侧栏和顶部上下文条；移动端折叠为水平工具条。当前项使用浅红背景、深色文字和明确的选中标识。

## Do's and Don'ts

### Do:

- **Do** 让作品缩略图、帧序列和 QA 问题成为页面主角。
- **Do** 为每个交互提供 hover、focus、disabled、loading 和 error 状态。
- **Do** 使用标准表格、筛选器、下拉菜单和对话框行为。
- **Do** 在 960px 以下重排工作台，在 720px 以下折叠侧栏。

### Don't:

- **Don't** 把界面做成泛化的 AI SaaS 营销页。
- **Don't** 使用紫色渐变、玻璃拟态、巨型圆角卡片或无意义动效。
- **Don't** 给卡片添加粗侧边彩条或同时叠加边框与宽模糊阴影。
- **Don't** 把每项功能包装成同样大小的图标卡片。
- **Don't** 让状态只依赖红、绿颜色区分。
