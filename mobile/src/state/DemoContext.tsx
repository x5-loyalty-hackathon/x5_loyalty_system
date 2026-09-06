import React, { createContext, useCallback, useContext, useRef, useState } from 'react';
import * as api from '../api/endpoints';
import type {
  Anchor, FulfillmentOption, HealthResponse, MealPlan, MealRecommendation, MealResponse,
  MealRoute, PlanRequest, ProductOption, ProgressSnapshot, RecommendationMode, HomeDecorationSnapshot,
} from '../api/types';
import { DEMO_NOW, DEFAULT_DEMO_PROFILE, DEMO_PROFILES } from '../fixtures/recommendationRequest';
import { kitchenProducts, mergeKitchenProducts, purchasedKitchenProducts } from '../domain/kitchen';
import { getCommerceHost, type CommerceHost } from '../domain/commerce';
import {
  acceptMeals, canCompleteCook, createRequestGate, makeBasket, makeDemoReceipt, makePlan, purchaseGroups, receiptNotice, rewardText,
} from '../domain/mealFlow';

type AsyncStatus = 'idle' | 'loading' | 'ready' | 'error';
interface Query { mode: RecommendationMode | null; anchor: Anchor; storeId: string | null }
interface PendingPlan { request: PlanRequest; products: ProductOption[] }
type DecorationAction = { kind: 'goal'; itemId: string | null } | { kind: 'apply'; itemId: string };
interface DecorationFailure { action: DecorationAction; message: string }
const initialQuery: Query = { mode: null, anchor: 'home', storeId: null };
const emptyBasket = { products: [], total: 0, savings: 0, error: 'Сначала выберите блюдо.' };
function useDemoState(commerceHost?: CommerceHost) {
  const isDemoCheckout = (commerceHost ?? getCommerceHost()).mode === 'demo';
  const [profile, setProfile] = useState(DEFAULT_DEMO_PROFILE);
  const profileRef = useRef(DEFAULT_DEMO_PROFILE);
  // A generation also distinguishes A → B → A: user ID alone cannot reject
  // a late response from the first visit to A.
  const session = useRef(0);
  const renderSession = session.current;
  const [response, setResponse] = useState<MealResponse | null>(null);
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [recipesStatus, setRecipesStatus] = useState<AsyncStatus>('idle');
  const [recipesError, setRecipesError] = useState<string | null>(null);
  const [query, setQuery] = useState<Query>(initialQuery);
  const queryRef = useRef(initialQuery);
  const gate = useRef(createRequestGate());
  const progressGate = useRef(createRequestGate());
  const [selectedMeal, setSelectedMeal] = useState<MealRecommendation | null>(null);
  const [route, setRoute] = useState<MealRoute>('cook');
  // Демо ведёт один сценарий: доставка и уценка предлагаются всегда. Выбор
  // способа получения вернётся, когда корзина начнёт уходить в доставку X5.
  const [fulfillment, setFulfillment] = useState<FulfillmentOption>('delivery');
  const [markdown, setMarkdown] = useState(true);
  const [choices, setChoices] = useState<Record<string, string>>({});
  const [book, setBook] = useState<string[]>([]);
  const [plan, setPlan] = useState<MealPlan | null>(null);
  const [cooking, setCooking] = useState(false);
  const [kitchenItems, setKitchenItems] = useState(kitchenProducts(DEFAULT_DEMO_PROFILE.currentReceipt.items));
  const kitchenReceipts = useRef(new Set<string>());
  const pendingPlan = useRef<PendingPlan | null>(null);
  const pendingReceipt = useRef<ReturnType<typeof makeDemoReceipt> | null>(null);
  const [busy, setBusy] = useState(false);
  const busyRef = useRef(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  // Поставленная косметика: id предмета -> стоит ли он на кухне. Открытие
  // считается от уровня и живёт на сервере, а выбор оформления — локальный.
  const [equipped, setEquipped] = useState<Record<string, boolean>>({});
  const [progress, setProgress] = useState<ProgressSnapshot | null>(null);
  const [progressStatus, setProgressStatus] = useState<AsyncStatus>('idle');
  const [progressError, setProgressError] = useState<string | null>(null);
  const [decoration, setDecoration] = useState<HomeDecorationSnapshot | null>(null);
  const [decorationStatus, setDecorationStatus] = useState<AsyncStatus>('idle');
  const [decorationError, setDecorationError] = useState<string | null>(null);
  const [decorationBusy, setDecorationBusy] = useState(false);
  const decorationBusyRef = useRef(false);
  // One gate for GET and mutations: an older GET cannot undo an applied wall.
  const decorationGate = useRef(createRequestGate());
  const decorationRefreshPending = useRef(false);
  const [decorationFailedAction, setDecorationFailedAction] = useState<DecorationAction | null>(null);
  const decorationFailure = useRef<DecorationFailure | undefined>(undefined);

  const clearSelection = useCallback(() => {
    setSelectedMeal(null); setChoices({}); setPlan(null); pendingPlan.current = null;
    pendingReceipt.current = null;
    setCooking(false);
    setActionError(null); setNotice(null);
  }, []);
  const switchProfile = (profileId: string) => {
    const next = DEMO_PROFILES.find((item) => item.id === profileId);
    if (!next || next.id === profileRef.current.id) return;
    session.current += 1;
    gate.current.next(); progressGate.current.next(); decorationGate.current.next();
    profileRef.current = next; setProfile(next);
    busyRef.current = false; setBusy(false);
    queryRef.current = initialQuery; setQuery(initialQuery);
    clearSelection(); setRoute('cook'); setFulfillment('delivery'); setMarkdown(true);
    setKitchenItems(kitchenProducts(next.currentReceipt.items)); kitchenReceipts.current = new Set();
    setEquipped({});
    setBook([]); setResponse(null); setHealth(null); setRecipesStatus('idle'); setRecipesError(null);
    setProgress(null); setProgressStatus('idle'); setProgressError(null);
    setDecoration(null); setDecorationStatus('idle'); setDecorationError(null); setDecorationFailedAction(null);
    decorationFailure.current = undefined;
    decorationBusyRef.current = false; setDecorationBusy(false); decorationRefreshPending.current = false;
  };
  const loadRecipes = useCallback(async (changes: Partial<Query> = {}) => {
    if (busyRef.current) return;
    const activeProfile = profileRef.current;
    const next = { ...queryRef.current, ...changes };
    queryRef.current = next; setQuery(next);
    const token = gate.current.next();
    // Browsing/reloading recommendations must not delete the current cart/task.
    setCooking(false); setResponse(null); setRecipesError(null); setRecipesStatus('loading');
    try {
      const [nextHealth, result, saved] = await Promise.all([
        api.getHealth(), api.getRecommendations(next.mode, next.anchor, next.storeId, activeProfile),
        api.getRecipeBook(activeProfile.userId),
      ]);
      if (!gate.current.isCurrent(token)) return;
      setResponse(acceptMeals(result)); setHealth(nextHealth); setBook(saved.saved_recipe_ids);
      setRecipesStatus('ready');
    } catch (error) {
      if (!gate.current.isCurrent(token)) return;
      setRecipesError((error as Error).message); setRecipesStatus('error');
    }
  }, [clearSelection]);

  const startEntry = (next: FulfillmentOption) => {
    if (busyRef.current) return;
    // The existing draft keeps its fulfillment until another meal is chosen.
    if (!selectedMeal) setFulfillment(next);
    void loadRecipes({ mode: null, storeId: null });
  };

  const loadProgress = useCallback(async () => {
    const token = progressGate.current.next();
    setProgressStatus('loading'); setProgressError(null);
    try {
      const result = await api.getProgress(profileRef.current.userId);
      if (!progressGate.current.isCurrent(token)) return;
      setProgress(result); setProgressStatus('ready');
    } catch (error) {
      if (!progressGate.current.isCurrent(token)) return;
      setProgressError((error as Error).message); setProgressStatus('error');
    }
  }, []);
  const loadHomeDecoration = useCallback(async (preserveFailure?: DecorationFailure) => {
    if (decorationBusyRef.current) { decorationRefreshPending.current = true; return; }
    const token = decorationGate.current.next();
    const userId = profileRef.current.userId;
    setDecorationStatus('loading');
    if (!preserveFailure) {
      setDecorationError(null); setDecorationFailedAction(null); decorationFailure.current = undefined;
    }
    try {
      const result = await api.getHomeDecoration(userId);
      if (!decorationGate.current.isCurrent(token)) return;
      if (result.user_id !== userId) throw new Error('Оформление получено для другого покупателя. Повторите загрузку.');
      setDecoration(result);
      const reconciled = !preserveFailure || (preserveFailure.action.kind === 'apply'
        ? result.applied_item_id === preserveFailure.action.itemId
        : result.goal_item_id === preserveFailure.action.itemId);
      setDecorationStatus(reconciled ? 'ready' : 'error');
      if (reconciled) {
        setDecorationError(null); setDecorationFailedAction(null); decorationFailure.current = undefined;
      }
    } catch (error) {
      if (!decorationGate.current.isCurrent(token)) return;
      setDecorationStatus('error'); setDecorationError(preserveFailure?.message ?? (error as Error).message);
    }
  }, []);
  const changeHomeDecoration = async (action: DecorationAction): Promise<boolean> => {
    if (decorationBusyRef.current || renderSession !== session.current) return false;
    const token = decorationGate.current.next();
    const isCurrent = () => renderSession === session.current && decorationGate.current.isCurrent(token);
    const userId = profileRef.current.userId;
    let failure: DecorationFailure | undefined;
    decorationBusyRef.current = true; setDecorationBusy(true);
    setDecorationError(null); setDecorationFailedAction(null); decorationFailure.current = undefined;
    try {
      const result = action.kind === 'goal'
        ? await api.setHomeDecorationGoal(action.itemId, userId)
        : await api.applyHomeDecoration(action.itemId, userId);
      if (!isCurrent()) return false;
      if (result.user_id !== userId) throw new Error('Оформление получено для другого покупателя. Повторите действие.');
      setDecoration(result); setDecorationStatus('ready');
      return true;
    } catch (error) {
      if (isCurrent()) {
        failure = { action, message: (error as { status?: number }).status === 409
          ? 'Эти обои ещё закрыты. Оформление осталось прежним; обновите доступ после задания.'
          : (error as Error).message };
        decorationFailure.current = failure;
        setDecorationStatus('error'); setDecorationFailedAction(action); setDecorationError(failure.message);
      }
      return false;
    } finally {
      if (isCurrent()) {
        decorationBusyRef.current = false; setDecorationBusy(false);
        if (decorationRefreshPending.current) {
          decorationRefreshPending.current = false; void loadHomeDecoration(failure);
        }
      }
    }
  };
  const chooseDecorationGoal = (itemId: string | null) => changeHomeDecoration({ kind: 'goal', itemId });
  const applyDecoration = (itemId: string) => changeHomeDecoration({ kind: 'apply', itemId });
  const retryHomeDecoration = () => decorationFailedAction
    ? changeHomeDecoration(decorationFailedAction) : loadHomeDecoration();
  const acceptProgress = (value: ProgressSnapshot) => {
    progressGate.current.next(); setProgress(value); setProgressStatus('ready'); setProgressError(null);
    // Re-read server access after rewards; never derive unlocks from local XP.
    if (value.avatar_xp > 0) void loadHomeDecoration(decorationFailure.current);
  };
  const run = async (operation: (isCurrent: () => boolean, userId: string) => Promise<void>): Promise<boolean> => {
    if (busyRef.current || renderSession !== session.current) return false;
    const isCurrent = () => renderSession === session.current;
    const userId = profileRef.current.userId;
    busyRef.current = true; setBusy(true); setActionError(null); setNotice(null);
    try { await operation(isCurrent, userId); return isCurrent(); }
    catch (error) { if (isCurrent()) setActionError((error as Error).message); return false; }
    finally { if (isCurrent()) { busyRef.current = false; setBusy(false); } }
  };
  const selectMeal = (mealId: string) => {
    if (busyRef.current || recipesStatus !== 'ready') return;
    const meal = response?.recommendations.find((item) => item.meal_id === mealId);
    if (!meal) return;
    if (selectedMeal?.meal_id === mealId && plan?.status !== 'completed') {
      // Preserve the draft, but allow a refreshed server offer after expiration
      // or a definitive rejection. Never replace an uncertain in-flight task.
      if (!pendingPlan.current) { setSelectedMeal(meal); setActionError(null); }
      return;
    }
    // Уценка предлагается всегда: сбрасывать флаг на каждый выбор блюда нельзя,
    // иначе уценённые товары исчезают из плана.
    clearSelection(); setSelectedMeal(meal); setRoute(meal.default_route);
    const variant = meal.default_route === 'cook' ? meal.cook_variant : meal.ready_variant;
    if (!variant?.fulfillment_options.includes(fulfillment)) {
      setFulfillment(variant?.fulfillment_options.includes('delivery') ? 'delivery' : variant?.fulfillment_options[0] ?? 'next_visit');
    }
  };
  const basket = selectedMeal
    ? makeBasket(selectedMeal, route, fulfillment, markdown, choices) : emptyBasket;
  const editable = !busy && !pendingPlan.current;
  const readyProduct = selectedMeal?.ready_variant?.fulfillment_options.includes(fulfillment)
    ? purchaseGroups(selectedMeal, 'ready', fulfillment, markdown)[0]?.options[0] ?? null : null;
  const chooseRoute = (next: MealRoute) => {
    if (busyRef.current || pendingPlan.current || !selectedMeal?.available_routes.includes(next)) return;
    const variant = next === 'cook' ? selectedMeal.cook_variant : selectedMeal.ready_variant;
    if (!variant?.fulfillment_options.includes(fulfillment)) {
      setActionError('Этот вариант недоступен для выбранного способа получения.'); return;
    }
    setRoute(next); setChoices({}); setActionError(null);
  };
  const chooseFulfillment = (next: FulfillmentOption) => {
    if (busyRef.current || pendingPlan.current) return;
    setFulfillment(next); setChoices({}); setActionError(null);
  };
  const chooseMarkdown = (next: boolean) => {
    if (busyRef.current || pendingPlan.current) return;
    setMarkdown(next); setChoices({}); setActionError(null);
  };
  /**
   * «Купить готовое» одним действием: маршрут, выбранный товар и готовая
   * корзина. Иначе человек попадал на план, где готовое блюдо ещё нужно
   * отметить, хотя вариант там всего один.
   */
  const takeReadyMeal = () => {
    if (renderSession !== session.current || busyRef.current || pendingPlan.current || !readyProduct) return false;
    setRoute('ready'); setChoices({ ready: readyProduct.sku_id }); setActionError(null);
    return true;
  };
  const chooseProduct = (group: string, skuId: string) => {
    if (busyRef.current || pendingPlan.current) return;
    setChoices((current) => ({ ...current, [group]: skuId })); setActionError(null);
  };
  const saveToBook = () => run(async (isCurrent, userId) => {
    const recipeId = selectedMeal?.cook_variant?.recipe_id;
    if (!recipeId) throw new Error('Для этого предложения нет рецепта для сохранения.');
    const result = await api.saveRecipe(recipeId, userId);
    if (!isCurrent()) return;
    if (!['created', 'duplicate'].includes(result.status)) throw new Error('Не удалось сохранить рецепт.');
    setBook(result.saved_recipe_ids); setNotice('Рецепт в книге. Его можно выбрать через «Повторить».');
  });
  const persistPlan = async (isCurrent: () => boolean, userId: string) => {
    if (!selectedMeal) throw new Error('Сначала выберите блюдо.');
    if (!pendingPlan.current) {
      pendingPlan.current = {
        request: makePlan(selectedMeal, route, fulfillment, basket, userId,
          `${userId}-mobile-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`, DEMO_NOW),
        products: basket.products,
      };
    }
    const result = await api.saveMealPlan(pendingPlan.current.request);
    if (!isCurrent()) return;
    if (!['created', 'duplicate'].includes(result.status) || !result.plan) {
      if (result.status === 'rejected') { pendingPlan.current = null; setPlan(null); }
      throw new Error('Сервер отклонил план. Выберите блюдо заново.');
    }
    setPlan(result.plan);
    if (result.progress) acceptProgress(result.progress);
    setNotice('План сохранён. Это не заказ и не бронь.');
    return result.plan;
  };

  const savePlan = () => run(async (isCurrent, userId) => { await persistPlan(isCurrent, userId); });

  /**
   * Короткий путь с карточки блюда, когда докупать нечего: задание создаётся и
   * готовка открывается сразу. Решение принимается по свежему ответу сервера,
   * а не по состоянию — оно на этом тике ещё пустое.
   */
  const savePlanAndCook = () => run(async (isCurrent, userId) => {
    const saved = await persistPlan(isCurrent, userId);
    if (!saved || !isCurrent()) return;
    if (!canCompleteCook(saved)) throw new Error('Сначала соберите продукты.');
    setCooking(true);
  });
  const canConfirmPurchase = Boolean(plan?.selected_product_ids.length && plan.status === 'saved');
  const acceptPurchase = async (
    receipt: ReturnType<typeof makeDemoReceipt>, pending: PendingPlan,
    isCurrent: () => boolean,
  ) => {
    if (receipt.user_id !== pending.request.user_id || receipt.meal_plan_id !== pending.request.plan_id) {
      throw new Error('Подтверждение покупки относится к другому покупателю или заданию.');
    }
    pendingReceipt.current = receipt;
    const result = await api.submitReceipt(receipt);
    if (!isCurrent()) return;
    acceptProgress(result.progress);
    if (result.meal_plan) setPlan(result.meal_plan);
    // Business rejection/review throws before kitchen display is changed.
    const message = receiptNotice(result);
    if (!kitchenReceipts.current.has(receipt.receipt.receipt_id)) {
      // A partial/unrelated receipt is not evidence that the entire cart arrived.
      const received = pending.products.filter((p) => receipt.receipt.items.some((item) => item.sku_id === p.sku_id));
      const purchased = purchasedKitchenProducts(selectedMeal!, pending.request.selected_route, received);
      kitchenReceipts.current.add(receipt.receipt.receipt_id);
      setKitchenItems((current) => mergeKitchenProducts(current, purchased));
    }
    // Keep the locked basket for retries; cooking never deletes whole packs.
    setNotice(`${isDemoCheckout ? 'Демо-покупка подтверждена. ' : ''}${message} ${rewardText(result.meal_plan)}`);
  };
  // Synthetic driver retained for API/regression tests, never used by game buttons.
  const confirmPurchase = () => run(async (isCurrent) => {
    if (!plan || !pendingPlan.current || !selectedMeal) throw new Error('Сначала выберите задание.');
    if (!canConfirmPurchase) throw new Error('Покупка уже подтверждена. Нового чека для этого плана не требуется.');
    const pending = pendingPlan.current;
    await acceptPurchase(pendingReceipt.current ?? makeDemoReceipt(pending.request, pending.products, DEMO_NOW), pending, isCurrent);
  });
  const checkout = () => run(async (isCurrent, userId) => {
    if (basket.error || !basket.products.length) throw new Error(basket.error ?? 'Докупать нечего — готовка доступна на Кухне.');
    if (plan && plan.status !== 'saved') throw new Error('Покупка уже учтена. Продолжите на Кухне.');
    // Recover the exact event first, including kitchen display. Re-saving a plan
    // can already return collected/completed after a lost receipt response.
    if (pendingReceipt.current && pendingPlan.current) {
      await acceptPurchase(pendingReceipt.current, pendingPlan.current, isCurrent); return;
    }
    // The standalone default models external checkout. It never bypasses plan
    // activation or receipt verification, and never replaces a failing real host.
    const host = commerceHost ?? getCommerceHost();
    const saved = await persistPlan(isCurrent, userId);
    if (!saved || !isCurrent()) return;
    if (saved.status !== 'saved') {
      setNotice(`Покупка уже учтена. Продолжите на Кухне. ${rewardText(saved)}`); return;
    }
    const pending = pendingPlan.current!;
    const result = await host.openCheckout({
      checkoutId: pending.request.plan_id,
      plan: { ...pending.request, selected_product_ids: [...pending.request.selected_product_ids] },
      products: pending.products.map((p) => ({ ...p, fulfillment_options: [...p.fulfillment_options] })),
    });
    if (!isCurrent()) return;
    if (result.status === 'cancelled') {
      // Explicit host cancellation means no order was placed. Preserve the draft
      // but allow editing and a new immutable task on the next checkout attempt.
      pendingPlan.current = null; setPlan(null);
      setNotice('Оформление отменено. Выбранные товары остались в корзине.'); return;
    }
    if (result.status !== 'purchased' || !result.receipt) throw new Error('Приложение не подтвердило покупку.');
    await acceptPurchase(result.receipt, pending, isCurrent);
  });
  const confirmCooking = () => run(async (isCurrent, userId) => {
    if (!plan || (!canCompleteCook(plan) && plan.status !== 'completed')) throw new Error('Сначала соберите продукты.');
    const result = await api.completeCook(plan.plan_id, userId);
    if (!isCurrent()) return;
    acceptProgress(result.progress);
    if (result.plan) setPlan(result.plan);
    if (!['completed', 'duplicate'].includes(result.status)) throw new Error('Готовка не подтверждена: проверьте план и покупку.');
    setCooking(false);
    setNotice(`${result.status === 'duplicate' ? 'Блюдо уже учтено; повторной награды нет.' : 'Блюдо добавлено в вашу историю.'} ${rewardText(result.plan)}`);
  });
  const startCooking = () => {
    if (busyRef.current || !canCompleteCook(plan)) return false;
    setCooking(true); setActionError(null); setNotice(null); return true;
  };
  const pauseCooking = () => { if (!busyRef.current) setCooking(false); };
  return {
    profile, profiles: DEMO_PROFILES, switchProfile,
    decoration, decorationStatus, decorationError, decorationBusy, decorationFailedAction,
    loadHomeDecoration, chooseDecorationGoal, applyDecoration, retryHomeDecoration,
    response, health, recipesStatus, recipesError, query, loadRecipes, startEntry, selectedMeal, selectMeal,
    route, chooseRoute, takeReadyMeal, readyProduct, fulfillment, chooseFulfillment, markdown, chooseMarkdown,
    choices, chooseProduct, basket, book, saveToBook, plan, savePlan, editable, busy,
    cooking, startCooking, pauseCooking, savePlanAndCook, kitchenItems,
    equipped,
    toggleUpgrade: (upgradeId: string) =>
      setEquipped((current) => ({ ...current, [upgradeId]: !current[upgradeId] })),
    actionError, notice, checkout, isDemoCheckout, canConfirmPurchase, confirmPurchase, confirmCooking, progress, progressStatus, progressError, loadProgress,
  };
}
type DemoValue = ReturnType<typeof useDemoState>;
const DemoCtx = createContext<DemoValue | null>(null);
export function DemoProvider({ children, commerceHost }: { children: React.ReactNode; commerceHost?: CommerceHost }) {
  return <DemoCtx.Provider value={useDemoState(commerceHost)}>{children}</DemoCtx.Provider>;
}
export function useDemo(): DemoValue {
  const value = useContext(DemoCtx);
  if (!value) throw new Error('useDemo вне DemoProvider');
  return value;
}
