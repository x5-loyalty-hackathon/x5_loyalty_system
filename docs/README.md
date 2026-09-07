# Карта документации

Начинать здесь; даты и хеши в исторических отчётах относятся к их снимкам.

## Действующие документы

- [Состояние](project-status.md) и [остаток до защиты](poc-readiness.md).
- [Запуск mobile](../mobile/README.md), [handoff PR #10](../mobile/docs/pr10-handoff.md),
  [общая карта интеграции](integration-handoff.md).
- [Журнал решений](decision-log.md): ADR-001–005. Исследовательские EXP-ADR
  не заменяют принятые системные решения.
- [Технический дизайн](technical-design.md), [checkout основного приложения](commerce-host.md),
  [safety каталога](catalog-safety.md), [метрики](metrics-api.md).
- [Показ антифрода/рефералов](safety-demo.md), [план пилота](pilot-plan.md),
  [handoff оценки](llm-eval-handoff.md).
- [Исходный safety-аудит](reviews/2026-09-07-poc-system-safety-audit.md) и
  [исправления с повторной проверкой](reviews/2026-09-07-safety-fixes.md).

## История и исследования — не текущая очередь задач

| Материалы | Как читать |
|---|---|
| [История статуса](project-status-history.md), [история чеклиста](poc-readiness-history.md) | Снимки 05–06.09, прежние UI/API и закрытые очереди |
| [План исполнения](poc-execution-plan.md), [план сведения веток](branch-merge-plan.md) | Сохраняют ответы команды и причины выбора; текущие действия — в чеклисте выше |
| [Первый план реализации](implementation-plan.md), [Day 1/test gates](mvp-scope-and-test-plan.md), [первый mobile-план](mobile-integration-plan.md), [frontend-план](frontend-demo-plan.md) | История планирования, не утверждения о составе сегодняшних экранов |
| [Контракт прежнего декора](home-decoration-contract.md) | Старые серверные обои/цель не подключены к десяти предметам нового UI |
| `reviews/`, [handoff PR #9](../mobile/docs/pr9-handoff.md) | Доказательства конкретных ревизий; новые проверки не переписывают старые числа |
| `submission/intermediate/` | Промежуточная сдача, не финальная версия продукта |
| `research/`, `eval/`, benchmark/sensitivity reports | Гипотезы и результаты конкретных методик; не доказательство реального uplift |

Исторические документы и личные черновики не удалены; прежние пути сохранены,
кроме выделенных архивов статуса/чеклиста. Их исходные пути теперь ведут на
короткие актуальные страницы. Файлы вне Git не публикуются автоматически.
