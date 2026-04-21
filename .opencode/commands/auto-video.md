---
description: 创建定时任务自动监控视频生成状态，下载完成视频，重试因并行限制失败的任务。使用 /auto-video ep01 启动，任务全部完成后自动停止。
agent: build
subtask: true
argument-hint: '[集数|all] [检查间隔秒数]'
---
`/auto-video` 在 opencode 端不支持自动定时监控（依赖 Cron 工具组）。
请使用操作系统调度调用 `/check-video <ep>`：

**macOS / Linux (cron)**：
```
*/5 * * * * cd /path/to/project && opencode run "/check-video ep01"
```

**macOS (launchd)**：见 README "OS 调度" 章节

**Windows (Task Scheduler)**：见 README "OS 调度" 章节
