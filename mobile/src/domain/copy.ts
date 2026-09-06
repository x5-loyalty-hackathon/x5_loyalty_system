/** Public texts mirrored from app/explanations.py; covered by parity test. */
export const reasonText: Record<string, string> = {
  "explicit_mode_request": "Тип челленджа выбран пользователем.",
  "current_basket_strategy": "Используем продукты из текущего чека.",
  "saved_recipe_strategy": "Предлагаем повторить сохранённый рецепт.",
  "novel_recipe_strategy": "Предлагаем новый для пользователя рецепт.",
  "selected_by_effort_then_relevance": "Это самый простой подходящий вариант: меньше докупок, затем выше релевантность.",
  "full_basket_requires_explicit_choice": "Для рецепта нужна полная новая корзина, поэтому он доступен только по выбору.",
  "current_receipt_overlap": "Часть ингредиентов уже есть в текущем чеке.",
  "category_history_match": "Эта категория встречалась в истории покупок.",
  "quick_recipe": "Приготовление занимает не больше 30 минут.",
  "low_missing_count": "Нужно докупить не больше двух продуктов.",
  "home_ingredient_reuse": "Используются продукты, отмеченные как имеющиеся дома.",
  "safe_markdown_option_available": "Есть прошедший проверку вариант по уценке.",
  "preferred_brand_option_available": "Среди вариантов есть предпочитаемый бренд.",
  "safe_ready_option_available": "Есть прошедший проверку вариант готового блюда.",
  "safe_recipe_available": "Рецепт можно безопасно собрать из доступных вариантов.",
  "explicit_cook_preference": "Пользователь предпочитает готовить.",
  "explicit_ready_preference": "Пользователь предпочитает готовую еду.",
  "prepared_food_share_supports_ready": "В истории покупок не меньше половины позиций приходится на готовую еду.",
  "ingredient_purchase_history_supports_cook": "История покупок больше соответствует приготовлению дома.",
  "cook_route_unavailable": "Безопасный вариант приготовления сейчас недоступен.",
  "ready_route_unavailable": "Безопасный вариант готового блюда сейчас недоступен.",
  "cook_route_fallback": "Поэтому используем доступный сценарий приготовления.",
  "ready_route_fallback": "Поэтому используем доступный вариант готового блюда.",
  "only_ready_route_available": "Сейчас доступен только вариант готового блюда.",
  "explicit_store_choice": "Точка выбрана пользователем.",
  "maximum_ingredient_coverage": "В этой точке доступно больше всего недостающих ингредиентов.",
  "preferred_store_for_anchor": "При равном покрытии выбрана привычная точка для этого места.",
  "nearest_store_tiebreak": "При равном покрытии выбрана ближайшая точка."
};
export const modeText = { current: 'Из покупок', repeat: 'Повторить', explore: 'Новое' };
export const sourceText = {
  receipt: 'Есть в недавнем чеке — проверьте дома', home: 'Отмечено как имеющееся дома',
  markdown: 'Есть уценка', full_price: 'Обычная цена', unavailable: 'Нет доступного товара',
};
export function explain(codes: string[]): string {
  return codes.map((code) => reasonText[code]).filter(Boolean).join(' ');
}
export function warningText(warning: string): string {
  if (warning === 'Markdown availability is best-effort: the item is not reserved.') {
    return 'Уценённый товар не забронирован. Перед покупкой проверьте наличие и срок годности.';
  }
  if (warning === 'No safe recommendations are currently available.') return 'Сейчас нет подходящих безопасных предложений.';
  return 'Предложение требует дополнительной проверки.';
}
export const money = (value: number) => `${value.toFixed(2).replace('.', ',')} ₽`;
