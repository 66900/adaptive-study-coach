# 设计来源与整合边界

- [tutor-skills](https://github.com/bevibing/tutor-skills)：借鉴逐题测验、错题追踪和掌握度
  统计的学习流程；未复制或安装其代码。
- [memory-retrieval-learning](https://github.com/lyndonkl/claude/blob/main/skills/memory-retrieval-learning/SKILL.md)：
  借鉴主动回忆、交错练习和检索式学习；未安装其代码。
- [Skill-Anything](https://github.com/SYuan03/Skill-Anything)：借鉴把多格式资料归一化为统一
  条目的思路；未安装其外部 API 或缓存体系。
- [Py-FSRS](https://github.com/open-spaced-repetition/py-fsrs)：使用 6.3.1 版进行调度，
  目标记忆率 0.90。

系统把“艾宾浩斯遗忘曲线”的目标落地为 FSRS：每次根据学习者实际反馈更新难度、稳定性和
下次到期时间，而不是机械使用固定的 1、2、4、7 天表。
