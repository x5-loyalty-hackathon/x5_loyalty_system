# Международные кейсы геймификации и loyalty

- Статус: исследовательский материал для последующей агрегации.
- Дата среза: 2026-09-02.
- Назначение: найти переносимые причинные механизмы и ограничения, а не выбрать
  концепцию за команду.
- Evidence: используется шкала E1–E4 из
  [`research-plan.md`](research-plan.md). Уровень относится к конкретному
  выводу о механике, а не к известности бренда.

## Короткий вывод

Самый сильный общий паттерн — не «игра поверх приложения», а короткий замкнутый
контур вокруг конкретного поведения: достижимая цель → автоматический прогресс →
понятная ценность → следующий релевантный шаг. Tesco и Carrefour наиболее близки
к X5 по категории; Duolingo даёт редкий публичный A/B-тест механики; Odyssey,
FuelBand и Walgreens показывают разные причины, по которым эффектный слой может
не стать устойчивым продуктом.

| Кейс | Статус | Что реально меняет | Лучшее доступное evidence |
|---|---|---|---|
| Starbucks Rewards challenges | active, переработан в 2026 | частоту, пробу товара, digital tender | E3: масштаб всей программы, не uplift challenges |
| Starbucks Odyssey | retired 31.03.2024 | brand education, collection, access | E4: запуск и закрытие; business outcome не раскрыт |
| Sephora Beauty Insider Challenges | active | исследование категорий и digital actions | E3: участие около 20% active clients; без контроля |
| Tesco Clubcard Challenges | active | incremental category spend и app use | E3: funnel и масштаб; uplift/маржа не раскрыты |
| Carrefour Challenges / Bonusland | active | category/brand spend, visits, digital | E3: vendor/press aggregates без метода контроля |
| McDonald's Monopoly | active campaign, fraud-damaged | app acquisition, визиты в промопериод | E3: 500 млн plays; причинный sales uplift не выделен |
| NikeFuel / Nike Run Club | hardware retired, software active | регулярность бега и mastery | E4: продукт и продолжение; causal outcome нет |
| Duolingo streaks | active | регулярную практику | E1: внутренние рандомизированные A/B-тесты |
| Walgreens Healthy Choices | retired / changed | self-tracking и health actions | E2: большая наблюдательная cohort, не causal |

Во всех кейсах ниже «почему» разделено на факт и интерпретацию. Закрытие не
приравнивается к провалу механики, а engagement — к росту частоты или маржи.

## 1. Starbucks Rewards: challenges внутри частого ритуала

**Продукт, рынок, период, статус.** Starbucks Rewards, прежде всего США и
Канада; программа активна, 10 марта 2026 года перезапущена с уровнями Green,
Gold и Reserve. Персональные Bonus Star offers, Double Star Days и games
сохранены.

**ЦА и контекст.** App-ready посетители кофеен с естественной частотой от
нескольких раз в месяц до нескольких раз в неделю. Основные jobs — быстро
заказать привычный напиток, получить экономию и иногда попробовать новое.
Высокая естественная частота делает короткие streak-like missions правдоподобнее,
чем в beauty или fashion.

**Behavioral target и loop.** Персональное предложение или challenge → один или
несколько квалифицирующих заказов → автоматическое отражение прогресса и Bonus
Stars → бесплатный продукт/скидка → следующий заказ. Возможные цели — добавить
визит, купить в другом daypart или попробовать категорию; приложение одновременно
служит идентификатором, заказом, оплатой и трекером.

**Награда и экономика.** Stars — cash-like валюта с ограниченными redemption
tiers; есть free food/drinks, бесплатные модификации и редкие experiences. В
версии 2026 статус меняет скорость накопления, а стоимость отдельных redemption
ограничена dollar cap. Unit economics Bonus Star challenges публично не
раскрыты; следовательно, нельзя считать любую покупку участника инкрементальной.

**Персонализация, social и privacy.** Официальные условия допускают настройку
offers по purchase behavior и preferences; offer индивидуален и не переносится.
Публичного leaderboard нет. Это снижает privacy/toxicity риск, но оставляет риск
непрозрачных различий в сложности и награде.

**Публичный результат и evidence.** В Q1 FY2025 было 34,6 млн 90-day active
members в США, а spend участников составлял 60% tender dollars в company-operated
stores. В FY2025 Rewards обеспечивал почти 60% выручки таких магазинов. Это
**E3 для масштаба программы**: участники изначально чаще и лояльнее, а отдельных
результатов games/challenges или контроля не опубликовано.

**Почему продолжается / меняется.** Факт: core Rewards пережил много итераций и
остаётся частью заказа и оплаты; Odyssey при этом закрылся. Интерпретация:
устойчивость скорее объясняет минимальный friction и близость награды к кофейному
ритуалу, а не сама визуальная «игровость».

**Переносимость в X5.** Проверять challenges как next-best action внутри уже
существующей транзакции, а не как отдельную игру. Нужен holdout на уровне
challenge и reward-only arm: метрики всей программы Starbucks ничего не говорят
об incremental value геймификации. Короткий coffee streak нельзя буквально
переносить на покупателя, который ходит за продуктами раз в неделю.

**Источники и неизвестное.**

- [Starbucks Card, Loyalty & Mobile Dashboard](https://investor.starbucks.com/files/doc_financials/2025/q1/Q1-FY25-Digital-IR-Dashboard.pdf),
  обновлён 2025-01-03.
- [Starbucks Rewards Terms of Use](https://www.starbucks.com/rewards/terms/),
  effective 2026-03-10.
- [Reimagined Starbucks Rewards launches](https://about.starbucks.com/press/2026/reimagined-starbucks-rewards-loyalty-program-launches-with-new-member-benefits/),
  2026-03-10.
- Неизвестны assignment logic, per-challenge take-up, control uplift, стоимость
  Stars и маржа после каннибализации.

## 2. Starbucks Odyssey: коллекция и статус, не дошедшие до масштаба

**Продукт, рынок, период, статус.** Закрытая beta в США: запуск для первой группы
в декабре 2022 года, закрытие 31 марта 2024 года.

**ЦА и контекст.** Подмножество Starbucks Rewards members и employees из
waitlist, готовое к web3/collectibles. Это digital-superfans, а не репрезентативная
аудитория массовой loyalty-программы.

**Behavioral target и loop.** Journey с квизом, мини-игрой или покупкой →
collectible Journey Stamp (NFT) и points → новый level → доступ к virtual classes,
merchandise, events или поездкам; некоторые stamps можно было купить и продать.
Это попытка создать persistent identity и coffee community между покупками.

**Награда и экономика.** Главная ценность — collection, rarity, access и
experience; часть stamps продавалась, а вторичный рынок добавлял спекулятивную
ценность. Стоимость поддержки, rewards и blockchain-партнёрства, как и net
economics, не опубликованы.

**Персонализация, social и privacy.** Социальность строилась вокруг закрытого
community и рынка коллекционных объектов. Публичная переносимость NFT создаёт
другой риск, чем privacy-safe avatar: владение и сделки видимы в blockchain,
ценность становится зависимой от рынка.

**Публичный результат и evidence.** Продукт так и остался closed beta; Starbucks
не раскрыл active users, retention, purchases или margin uplift. Продажи NFT на
вторичном рынке показывают интерес узкого сегмента, но не loyalty outcome.
Закрытие подтверждено; это **E4**, а не доказательство отрицательного uplift.

**Почему закрыт.** Факт: Starbucks объяснил завершение beta подготовкой к
следующему этапу; открытого rollout не случилось. Интерпретация независимых
разборов: отдельный web-опыт, сложная технология, ограниченная доступность и
зависимость от NFT-cycle ухудшили путь к массовой полезности. Причинная версия
не подтверждена внутренними данными.

**Переносимость в X5.** Переносимы коллекция с осмысленной utility и редкий
access-reward; не переносимы blockchain и tradable scarcity как самоцель.
Persistent avatar должен отвечать «что он помогает делать после новизны?», быть
встроен в основной app flow и тестироваться отдельно от challenge и награды.

**Источники и неизвестное.**

- [Анонс Starbucks и Polygon](https://polygon.technology/blog/starbucks-taps-polygon-for-its-starbucks-r-odyssey-web3-experience-nbsp),
  2022-09-12.
- [TechCrunch: запуск первой beta-группы](https://techcrunch.com/2022/12/08/starbucks-opens-up-its-blockchain-based-loyalty-program-and-nft-community-to-first-beta-testers/),
  2022-12-08.
- [The Block: закрытие beta](https://www.theblock.co/news/business/2024-03-16-starbucks-odyssey-beta-closure-282934),
  2024-03-16.
- [Econsultancy: post-mortem loyalty design](https://econsultancy.com/starbucks-nft-loyalty-lessons/),
  март 2024; доступ 2026-09-02.
- Неизвестны размер beta, repeat rate, влияние на Starbucks purchases и полная
  стоимость программы.

## 3. Sephora Beauty Insider Challenges: discovery вместо ежедневной привычки

**Продукт, рынок, период, статус.** Beauty Insider Challenges в Северной
Америке, запущены в 2023 году и активны. Это компонент Beauty Insider, а не
отдельная игра.

**ЦА и контекст.** Покупатели prestige beauty; категория естественно реже
grocery, зато сильнее связана с discovery, routine, expertise, identity и
community. Tier Rouge требует $1 000 расходов в год; это уже высоколояльный
сегмент с риском малого headroom.

**Behavioral target и loop.** Пользователь вступает в тематический challenge →
выполняет набор действий, например покупает продукт новой категории или
заполняет skin-routine quiz → видит completed task → получает points и bonus за
набор → выбирает sample, product, discount или experience в Rewards Bazaar.
Не все действия требуют покупки, что помогает собирать zero-party data и обучать
discovery.

**Награда и экономика.** Базово участник получает не менее 1 point за $1;
500 points можно было обменивать на $10 Beauty Insider Cash, также есть samples,
birthday gifts и experiences. У некоторых digital redemptions есть minimum
purchase. Challenge economics и supplier funding публично не раскрыты.

**Персонализация, social и privacy.** Quiz и category actions дают данные о
routine и предпочтениях. Отдельная Beauty Insider Community поддерживает advice,
looks и product discovery, но challenge не требует публичного рейтинга. Skin и
beauty preferences требуют ясного consent; публичное сравнение «красоты» было бы
неприемлемо.

**Публичный результат и evidence.** В декабре 2024 года руководитель loyalty
сообщала о 40+ млн members против 25 млн в 2021 году и участии почти 20% active
client base хотя бы в одном challenge. Это **E3 для adoption**, но рост базы
нельзя приписать challenges: программа одновременно меняла events, shipping,
cash rewards и другие benefits; business uplift не дан.

**Почему продолжается.** Факт: Sephora планировала новые challenges и
эксперименты с duration/tasks. Интерпретация: механика подходит редкой категории,
потому что создаёт маршрут discovery и expertise, а не требует ежедневной
покупки. При этом cash-like points остаются значимой частью мотивации.

**Переносимость в X5.** Переносим «полезный маршрут» из транзакционных и
нетранзакционных шагов: например, открыть персональную подборку → выбрать цель →
попробовать одну релевантную категорию. Нельзя копировать beauty identity или
годовые spend tiers без проверки ЦА. Нужна метрика category breadth/margin, а не
только completion.

**Источники и неизвестное.**

- [Sephora Community: запуск Beauty Insider Challenges](https://community.sephora.com/t5/Trending-at-Sephora/Updated-10-3-Introducing-Beauty-Insider-Challenges-the-NEWEST/m-p/6822696),
  2024-02-01, обновлено 2025-04-24.
- [Modern Retail: интервью с руководителем Beauty Insider](https://www.modernretail.co/marketing/emmy-brown-berlind-sephora-modern-retail-vanguard-2024/),
  2024-12-11.
- [Sephora: эволюция Beauty Insider и Rewards Bazaar](https://newsroom.sephora.com/sephora-north-america-evolves-its-beauty-insider-program/),
  2020-05-28.
- [Sephora Beauty Insider Terms](https://www.sephora.com/beauty/terms-conditions-beauty-insider),
  версия 2025; доступ 2026-09-02.
- Неизвестны completion funnel, incremental category trial, повторная покупка,
  reward liability и маржа challenge cohort.

## 4. Tesco Clubcard Challenges: наиболее близкий AI challenge benchmark

**Продукт, рынок, период, статус.** Великобритания; pilot и первый rollout с мая
2024 года, затем четыре шестинедельные кампании и продолжение механики.

**ЦА и контекст.** Домохозяйства с Clubcard и достаточной историей корзин.
Grocery — высокая частота и широкий ассортимент, поэтому есть headroom не только
в визитах, но и в category/brand breadth. Cold start и invited-only eligibility
остаются ограничениями.

**Behavioral target и loop.** Invite в app/email → выбрать до 10 из 20
персональных spend challenges → покупки автоматически двигают progress bar в
течение шести недель → points выдаются за достигнутый порог → возврат в app и
следующая покупка. Примеры: потратить заданную сумму на BBQ range или plant-based
ready meals.

**Награда и экономика.** До 5 000 points, то есть £50 в Tesco или до £100 у
Reward Partners. Eagle Eye заявляет, что модель принимает более 190 решений,
подбирает product group, threshold и reward выше прогнозируемого organic spend;
участвуют own label и supplier-funded brands. Это описание design intent, не
публичная проверка incremental margin.

**Персонализация, social и privacy.** 1:1 offer по shopping habits, но с выбором
из нескольких целей; social layer и leaderboard отсутствуют. Главный риск —
необъяснимо высокий threshold или ощущение несправедливости между households.

**Публичный результат и evidence.** В 2024 году охват вырос до 10 млн members;
Tesco сообщил о более чем 0,5 млрд extra Clubcard points и рекордном digital
engagement. Vendor сообщает: 76% уникальных посетителей страницы начали играть,
62% players достигли первой награды. Это **E3**: denominator начинается после
визита на страницу, а control uplift, margin и cannibalization не опубликованы.

**Почему масштабирован.** Факт: после trial Tesco провёл четыре кампании и
увеличивал аудиторию. Интерпретация: сильны автоматический checkout tracking,
choice, релевантная категория и delayed goal-gradient; не доказано, какая доля
эффекта принадлежит game framing, а какая — крупной cash-like награде.

**Переносимость в X5.** Это ближайшая референсная архитектура для PoC:
персональный threshold, автоматический прогресс, reward cap, supplier funding.
Нужно улучшить доказательность: random holdout, предсказанный organic baseline,
маржа после награды и отдельный arm «тот же offer без progress/game».

**Источники и неизвестное.**

- [Tesco: анонс Clubcard Challenges](https://www.tescoplc.com/tesco-brings-its-ai-game-to-new-clubcard-challenges),
  2024-04-29.
- [Tesco Interim Results 2024/25](https://www.tescoplc.com/media/qjejufrm/tesco-plc-interim-results-2425-press-release.pdf),
  2024-10-03.
- [Tesco Annual Report 2025](https://www.tescoplc.com/media/ky0bfwpo/tesco_ar25_interactive.pdf),
  2025.
- [Eagle Eye case study](https://eagleeye.com/case-studies/tesco-clubcard-challenges),
  без даты; доступ 2026-09-02. Источник — поставщик решения.
- [MoneySavingExpert: правила второго раунда](https://www.moneysavingexpert.com/news/2024/07/tesco-clubcard-challenges-second-round/),
  2024-07-16.
- Неизвестны feature set модели, success по сегментам, A/B uplift, fraud rate и
  net incremental margin.

## 5. Carrefour Challenges и Bonusland: долгий grocery precursor

**Продукт, рынок, период, статус.** Challenges Bonus / Bonusland у Carrefour
Belgium с 2018 года; платформа игр, contests и savings actions активна и в 2026
году. Сходная technology line использовалась Carrefour France.

**ЦА и контекст.** Держатели Bonus Card с grocery-историей; частый shopping
cycle. Отдельные кампании рассчитаны на reactivation/digitalization, а
персональные challenges — на уже известные preferences. Эти цели нельзя смешивать.

**Behavioral target и loop.** Пользователь выбирает предложенные по истории
brands/categories → за несколько недель накапливает spend → проходит обычно три
персональных порога → получает Bonus Points/coupon. Bonusland дополнительно
объединяет временные games и contests и раз в две недели сообщает progress.

**Награда и экономика.** Cash-like points, coupons, sponsor gifts и chance prizes.
Supplier participation может финансировать campaign; vendor заявляет setting
threshold выше predicted natural behavior. Публичной декомпозиции reward cost и
retailer/supplier funding нет.

**Персонализация, social и privacy.** Challenges используют историю Bonus Card;
пользователь явно выбирает action. Социальность минимальна, публичного grocery
leaderboard нет. Текущие правила ограничивают один Bonusland account на Bonus
Card account и удаляют адрес доставки физического приза не позднее двух месяцев
после акции.

**Публичный результат и evidence.** В 2019 году vendor через отраслевое медиа
заявлял +10–12% spend участников, один дополнительный monthly visit и ROI 7;
отдельная campaign Carrefour France дала в четыре раза больше players, чем
обычные digital operations, и 100 тыс. rewards. Метод, контроль и net margin не
раскрыты; self-selection вероятен. Это **E3**, не causal proof.

**Почему продолжается.** Факт: Bonusland и weekly challenges доступны спустя
годы; supplier Eagle Eye продолжает продавать этот pattern другим grocers.
Интерпретация: устойчивость обеспечивают повторно используемая campaign platform
и привязка к чеку, но она не доказывает, что настольная тема или animation дают
incremental effect.

**Переносимость в X5.** Полезны три порога вместо all-or-nothing, автоматический
progress и общий campaign container. При агрегации нельзя сложить vendor ROI,
players и visits как независимые доказательства: они происходят из одной
technology/PR-линии и не раскрывают selection bias.

**Источники и неизвестное.**

- [Carrefour Belgium: текущие правила Bonusland](https://www.carrefour.be/fr/terms-and-conditions/bonusland),
  страница без даты; доступ 2026-09-02.
- [Carrefour: отслеживание progress и thresholds](https://www.carrefour.fr/faq?question=comment-suivre-la-progression-de-mes-challenges),
  страница без даты; доступ 2026-09-02.
- [e-marketing.fr: ранние результаты Challenges Carrefour/Auchan](https://www.e-marketing.fr/Thematique/retail-1095/Breves/Carrefour-Auchan-ROI-leurs-programmes-fidelite-gamifies-340858.htm),
  2019-07-01; vendor-provided results.
- [Carrefour France campaign case](https://jai-un-pote-dans-la.com/gamification-retail-focus-operation-carrefour/),
  2020-06-18; материал основан на коммуникации поставщика/Carrefour.
- Неизвестны текущий MAU, challenge-level control uplift, распределение ROI,
  margin, fatigue и fraud.

## 6. McDonald's Monopoly: масштабная acquisition-game и ценный fraud lesson

**Продукт, рынок, период, статус.** Временная промоакция с 1987 года на разных
рынках. После почти десятилетнего перерыва вернулась в США в октябре 2025 года;
в Великобритании и других странах проводилась регулярно. Статус — active campaign,
не постоянный meta-layer.

**ЦА и контекст.** Массовая fast-food аудитория, включая ностальгирующих взрослых
и app-ready пользователей. Естественная частота выше beauty, но акция создаёт
короткий пик, а не обязательно устойчивую привычку.

**Behavioral target и loop.** Qualifying item или legal no-purchase entry →
physical/digital game piece → instant reveal либо property collection → prize,
незавершённый set и возврат → ввод/claim в McDonald's app. В 2025 году app стал
центром collection и redemption, поэтому отдельная цель — digital acquisition.

**Награда и экономика.** Free food, partner discounts, merchandise и очень
редкие крупные prizes. Chance и искусственная редкость позволяют обещать крупный
jackpot при ограниченном expected cost; sponsor prizes снижают прямую стоимость.
Но headline prize не равен ожидаемой ценности для пользователя.

**Персонализация, social и privacy.** Механика почти не персонализирована;
collection стимулирует обмен и обсуждение. Для крупных claims собираются имя,
дата рождения, контакты и адрес, но публичный customer leaderboard не нужен.

**Публичный результат и evidence.** McDonald's сообщил почти о 500 млн plays в
США в 2025 году и назвал Monopoly одним из крупнейших digital customer
acquisition events; тогда было около 46 млн 90-day active app users. Q4 US comp
sales выросли 6,8%, но одновременно действовали value meals и Grinch campaign.
Это **E3**, не изолированный Monopoly uplift.

**Fraud и текущие controls.** В 1995–2001 годах директор security подрядчика
перенаправил минимум $20 млн high-value pieces связанным «победителям». Это был
privileged insider fraud в supply chain, а не аномалия покупательских чеков.
Правила UK 2025 используют independently audited seeding, single-use codes,
сохранение оригинала, household prize limits, identity/address verification и
право void counterfeit/tampered claims.

**Почему продолжена несмотря на скандал.** Факт: promotion вернулась и получила
массовое digital engagement после изменения операционных controls. Интерпретация:
узнаваемый collection loop и rare chance по-прежнему работают для acquisition;
это не подтверждает долгосрочный loyalty effect.

**Переносимость в X5.** Полезны single-use claim graph, separation of duties,
audit trail и step-up verification только для дорогой награды. Непереносим вывод
«500 млн plays = рост покупок». Sweepstakes может отвлечь от персональности,
требует отдельной legal модели и не решает конфликт существующих игр X5.

**Источники и неизвестное.**

- [McDonald's: возврат Monopoly в США](https://corporate.mcdonalds.com/corpmcd/our-stories/article/monopoly-returns-more-chances-towin.html),
  2025-09-29.
- [McDonald's Q4 2025 earnings call transcript](https://www.earningscall.ai/stock/transcript/MCD-2025-Q4),
  2026-02-11; слова менеджмента, сторонний хостинг.
- [US Department of Justice: arrests in promotional fraud](https://www.justice.gov/archive/opa/pr/2001/August/422ag.htm),
  2001-08-21.
- [US Court of Appeals: описание схемы и суммы diverted prizes](https://media.ca11.uscourts.gov/opinions/pub/files/200614726.pdf),
  2007-06-22.
- [McDonald's UK Monopoly Consumer Rules 2025](https://www.mcdonalds.com/gb/en-gb/terms-and-conditions/monopoly-consumer-rules-2025.html),
  правила кампании 2025; доступ 2026-09-02.
- Неизвестны incremental visits, retention новых app users, expected prize cost
  на игрока и false-positive rate новых controls.

## 7. NikeFuel / FuelBand → Nike Run Club: utility пережила оболочку

**Продукт, рынок, период, статус.** FuelBand вышел в 2012 году; Nike свернул
собственную wearable-hardware стратегию в 2014–2015 годах и прекратил legacy
sync services 30 апреля 2018 года. Nike Run Club (NRC) остаётся активным.

**ЦА и контекст.** Люди с намерением бегать или тренироваться; natural cadence
ежедневная/еженедельная, действие само имеет intrinsic health/mastery value.
Покупка обуви не нужна для каждой игровой сессии, поэтому app поддерживает бренд
между редкими retail transactions.

**Behavioral target и loop.** Run/track → pace, distance, PR и streak feedback →
trophy, monthly goal, guided plan или friend/community challenge → следующий run.
NikeFuel пытался свести разные активности к универсальному score; NRC сузил
ценность вокруг реального runner job.

**Награда и экономика.** Виртуальные achievements, self-improvement, coaching,
community и brand affinity; cash-like reward не обязателен. Это снижает reward
liability, но требует дорогой полезной функции — точного tracking и content.

**Персонализация, social и privacy.** Personal goals, guided plans, friend
challenges и opt-in live location. Социальное сравнение естественно только среди
сопоставимых runners; global leaderboard подвержен impossible mileage и cheating.
Location и health data чувствительнее grocery purchases.

**Публичный результат и evidence.** Официальный NRC описывает активные features,
но Nike не публикует causal retention, exercise uplift или shoe sales от них.
CEO в 2014 году подтвердил стратегический переход от hardware к software; это
**E4** для механики и причин закрытия, не business success evidence.

**Почему changed / retired.** Факт: hardware и legacy sync закрыты, software loop
сохранился. Интерпретация: proprietary device проиграл более универсальным
wearables/phones и создавал hardware burden. Закрытие sync с коротким notice
показывает, что «persistent» progress не должен зависеть от брошенного носителя.

**Переносимость в X5.** Переносимы self-comparison, маленькие friend cohorts,
utility и non-cash mastery. Но grocery purchase не обладает той же intrinsic
ценностью, что run: badge/аватар не создаст её автоматически. Persistent progress
нуждается в data export/recovery и не должен исчезать вместе с одной кампанией.

**Источники и неизвестное.**

- [Nike Run Club product page](https://www.nike.com/nrc-app),
  текущая страница; доступ 2026-09-02.
- [Nike Help: NRC challenges](https://www.nike.com/us/help/a/nrc-challenges),
  текущая страница; доступ 2026-09-02.
- [TIME: CEO confirms shift away from wearables](https://time.com/78223/nike-mark-parker-fuelband-wearable/),
  2014-04-26.
- [WatchGeneration: прекращение legacy services](https://www.watchgeneration.fr/sport/2018/04/fin-de-parcours-pour-le-fuelband-et-les-autres-appareils-de-nike-7602),
  2018-04-17; независимый источник с текстом уведомления Nike.
- Неизвестны NRC MAU/retention, связь app use с commerce и величина cheating.

## 8. Duolingo streaks: сильный механизм с неправильной для grocery частотой

**Продукт, рынок, период, статус.** Глобальная learning app; streak, streak
freeze/wager, leagues, quests и Friend Streak активны и постоянно меняются.

**ЦА и контекст.** Пользователи, которые хотят сформировать daily learning habit;
один урок занимает минуты и может быть выполнен каждый день без денег. Поэтому
frequency fit принципиально отличается от походов за продуктами.

**Behavioral target и loop.** Reminder → короткий урок → немедленное продление
streak/XP/path progress → loss aversion, soft-currency commitment или
accountability другу → возврат завтра. Streak Wager требует поставить внутреннюю
валюту и возвращает удвоенную ставку после семи дней; Weekend Amulet/Freeze
смягчает потерю progress.

**Награда и экономика.** В основном soft currency, status, collection и mastery;
предельная monetary cost мала. Revenue приходит от ads/subscription, поэтому
daily use имеет прямую ценность, но компания отдельно следит, чтобы игра не
заменяла обучение.

**Персонализация, social и privacy.** Пользователь выбирает goal; напоминания
персонализированы. Friend Streak ограничен пятью друзьями и создаёт mutual
accountability без публичного имени/адреса в глобальном рейтинге.

**Публичный результат и evidence.** Во внутреннем рандомизированном A/B-тесте
предложение Streak Wager дало статистически значимый рост D1/D7/D14 retention,
максимум **+14% D7**; Weekend Amulet дал **+4%** вероятности вернуться через
неделю и **−5%** вероятности потерять streak. Это **E1**, хотя sample size и
absolute baseline не раскрыты. В 2024 году 10+ млн users имели streak не менее
года, а треть DAU — Friend Streak; это только E3.

**Почему продолжается / меняется.** Duolingo обнаружил, что XP leaderboards
могут разгонять grinding у уже активных users, а sessions не равны learning.
Поэтому Monthly Challenge сменили с XP на quests, а guardrail стал Time Spent
Learning Well. Это важнее самой цифры streak: target metric защищён от игрового
proxy.

**Переносимость в X5.** Переносимы explicit commitment, grace/freeze, social
accountability с одним другом и guardrail против farming. Для X5 cadence должен
быть «выполни плановый weekly action» или «не пропусти следующую ожидаемую
покупку», а не daily purchase streak. Иначе механика создаёт лишние походы,
food waste или субсидирует органику.

**Источники и неизвестное.**

- [Duolingo: streak A/B tests](https://blog.duolingo.com/how-streaks-keep-duolingo-learners-committed-to-their-language-goals/),
  исходная публикация 2017; доступ 2026-09-02.
- [Duolingo FY2024 shareholder letter / Form 8-K](https://investors.duolingo.com/static-files/d0adccff-bfe0-4d10-a5bc-f116d746afd2),
  2025-02-27.
- [Duolingo: Friend Streak product lessons](https://blog.duolingo.com/product-lessons-friend-streak/),
  2024; доступ 2026-09-02.
- [Duolingo: Time Spent Learning Well](https://blog.duolingo.com/time-spent-learning-well/),
  2024; доступ 2026-09-02.
- Неизвестны размеры A/B cells, absolute retention, heterogeneous effects и
  влияние streak wager на learning outcome, а не только return.

## 9. Walgreens Balance Rewards for healthy choices: награда за proxy и fatigue

**Продукт, рынок, период, статус.** США; Balance Rewards for healthy choices
(BRhc) действовал в 2010-х, в 2020 году был переведён в myWalgreens Health Goals,
а cash rewards за Health Goals прекращены 16 ноября 2022 года.

**ЦА и контекст.** Покупатели pharmacy/health retail, в том числе люди с
хроническими состояниями и пользователи wearables. Частота health action высокая,
но store visit значительно ниже; digital readiness неоднородна.

**Behavioral target и loop.** Set goal или connect device → walk/run/cycle,
weigh-in, blood pressure/glucose log, prescription или immunization → points и
progress → Walgreens discount → повторный tracking. Manual entry и automatic
device sync сосуществовали.

**Награда и экономика.** Например, 20 points за mile или log и caps по периоду;
points конвертировались примерно в $1 за 1 000. Employer/health plan мог
финансировать только фактически выданные points. Reward cash-like и отделён от
маржи конкретной retail mission, что усложняет economics.

**Персонализация, social и privacy.** Goal choice и connected device дают
индивидуальный path; public social competition не нужна. Собираются biometrics и
health behavior. В white paper отдельно указано, что переданная online
personally identifiable information не покрывалась HIPAA/Notice of Privacy
Practices программы — серьёзный consent и trust risk.

**Публичный результат и evidence.** Исследование 455 341 users за 2014 год:
**34% прекратили после единственной записи**; среди сделавших записи минимум в
два разных дня median participation был 8 недель. Automatic-device users
участвовали в среднем 20 недель против 5 у manual users. Это большая
наблюдательная cohort, **E2 для association**, но device owners self-select и
эффект incentives не отделён.

**Почему changed / retired.** Факт: Walgreens заменил сложные points на более
понятные percentages/Walgreens Cash, а позже прекратил rewards за Health Goals;
причина последнего решения не раскрыта. Нельзя называть BRhc полным провалом:
часть users удерживалась долго, но массовый early drop-off и закрытие rewards
показывают предел cash incentive вокруг logging.

**Переносимость в X5.** Автоматический чек лучше ручного ввода: меньше friction и
fraud surface. Нельзя награждать легко подделываемый proxy, если business target —
покупка/маржа; и не следует собирать health data для grocery game без
необходимости. Early drop-off нужно показывать в funnel, а не скрывать aggregate
users и miles.

**Источники и неизвестное.**

- [Walgreens white paper: Small Steps, Big Benefits](https://www.walgreens.com/assets/healthcare-solutions/pdf/abstracts/BalanceRewardsWhitePaper_Digital_20150605.pdf),
  2015-06; corporate data.
- [JMIR: Self-Monitoring Utilization Patterns](https://www.jmir.org/2016/11/e292),
  2016-11-17.
- [Walgreens: переход на myWalgreens и упрощение currency](https://corporate.walgreens.com/news-and-stories/stories/retail-customer-experience/just-mywalgreens-all-yours/),
  ноябрь 2020; доступ 2026-09-02.
- [Walgreens FAQ: Health Goals rewards discontinued](https://www.walgreens.com/topic/promotion/mywalgreens.jsp),
  effective 2022-11-16; доступ 2026-09-02.
- Неизвестны причины закрытия Health Goals, causal health outcome, retail uplift,
  fraud rate и полная reward cost.

## Anti-patterns, которые нельзя унести в X5 без проверки

1. **Считать engagement бизнес-эффектом.** Plays, app opens, NFT turnover,
   challenge starts и achievement rate не заменяют incremental visits и margin.
2. **Приписывать механике результат всей loyalty-программы.** Доля продаж
   Starbucks Rewards и рост базы Sephora включают payment, discounts, ordering,
   events и бренд; games — только один компонент.
3. **Копировать cadence другой категории.** Daily streak естественен для
   трёхминутного урока, но может поощрять ненужные покупки и food waste в grocery.
4. **Добавлять оболочку раньше behavioral mechanism.** NFT, avatar, board или
   animation не отвечают, какое действие и почему должно измениться после
   novelty period.
5. **Награждать органику.** Персонализация по любимой категории без
   counterfactual threshold часто просто субсидирует уже запланированную корзину.
6. **Путать self-selection с uplift.** Участники, посетители challenge page,
   connected-device users и VIP members уже отличаются от контроля.
7. **Оптимизировать игровой proxy.** XP grinding у Duolingo и manual health logs
   показывают, как score отрывается от полезного результата. Для X5 это могут
   быть split checks, дешёвые SKU или фиктивные referrals.
8. **All-or-nothing или непрозрачный threshold.** Недостижимая цель демотивирует,
   а разные персональные условия без объяснения воспринимаются как
   несправедливость. Нужны reachable tiers и краткое «почему эта цель вам».
9. **Открытый глобальный leaderboard.** Он сравнивает несопоставимых users,
   награждает power users и притягивает cheating. Предпочтительнее self-progress,
   small opt-in cohorts или percentile без ФИО.
10. **Сосредоточить дорогую награду в одной привилегированной точке.** История
    Monopoly требует separation of duties, audited issuance, immutable claim log
    и step-up verification, а не только чековый anomaly score.
11. **Маскировать sponsor coupon под prize value.** Номинал с minimum purchase,
    expiry или auto-renewal не равен воспринимаемой и фактической стоимости.
12. **Создать persistent asset без continuity promise.** Закрытые Odyssey и
    FuelBand показывают риск прогресса, который теряет utility при смене
    платформы. Нужны recovery, portability и понятный end-of-life.
13. **Собирать лишние identity/health/location data.** Для челленджа не нужны
    ФИО, адрес или biometrics; verification должна усиливаться только вместе с
    риском и ценностью claim.
14. **Не давать безопасно пропустить период.** Grace/freeze снижает разрушение
    накопленного progress и pressure; отсутствие forgiveness превращает habit в
    punishment.

## Что вынести в общую агрегацию и брейншторм

- Наиболее близкий baseline для X5 — не Starbucks или Duolingo, а связка
  Tesco/Carrefour: purchase-history → несколько достижимых целей → авто-progress
  по чеку → tiered reward → holdout по incremental margin.
- Наиболее доказанный отдельный механизм — voluntary commitment с soft currency
  и forgiveness у Duolingo. Переносить следует commitment/grace, но не daily
  cadence.
- Сильная неденежная мотивация возникает там, где продукт даёт самостоятельную
  utility: coaching у NRC, discovery/expertise у Sephora. Для X5 сначала надо
  назвать такую utility; avatar не является ею сам по себе.
- Chance-based campaign может быстро привлечь пользователей, но McDonald's
  показывает одновременно слабую причинную интерпретацию и широкий fraud
  perimeter.
- Для аватара минимальный component test: одинаковые сегмент, challenge, reward
  и коммуникация; arm A без аватара, arm B с persistent avatar/progress. Иначе
  uplift нельзя отнести к аватару.
- Для персонализации минимальный тест: generic achievable challenge,
  personalized challenge, personalized reward-only offer и no-offer control.
  Guardrails: reward cost, gross margin/user, organic purchase cannibalization,
  suspicious checks/referrals, opt-out и complaint rate.

Исследование не отвечает, какой сегмент и механика нужны X5. Оно задаёт фильтр:
идея должна иметь frequency fit, полезность после novelty, измеримый
counterfactual и экономику, переживающую reward cost и fraud.
