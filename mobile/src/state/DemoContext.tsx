import React, { createContext, useCallback, useContext, useRef, useState } from 'react';
import * as api from '../api/endpoints';
import type {
  Anchor, FulfillmentOption, HealthResponse, MealPlan, MealRecommendation, MealResponse,
  MealRoute, PlanRequest, ProductOption, ProgressSnapshot, RecommendationMode,
} from '../api/types';
import { DEMO_NOW, DEMO_USER_ID } from '../fixtures/recommendationRequest';
import {
  acceptMeals, canCompleteCook, createRequestGate, makeBasket, makeDemoReceipt, makePlan, receiptNotice,
} from '../domain/mealFlow';

type AsyncStatus = 'idle' | 'loading' | 'ready' | 'error';
interface Query { mode: RecommendationMode | null; anchor: Anchor; storeId: string | null }
interface PendingPlan { request: PlanRequest; products: ProductOption[] }
const initialQuery: Query = { mode: null, anchor: 'home', storeId: null };
const emptyBasket = { products: [], total: 0, savings: 0, error: 'Сначала выберите блюдо.' };
function useDemoState() {
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
  const [fulfillment, setFulfillment] = useState<FulfillmentOption>('next_visit');
  const [markdown, setMarkdown] = useState(false);
  const [choices, setChoices] = useState<Record<string, string>>({});
  const [book, setBook] = useState<string[]>([]);
  const [plan, setPlan] = useState<MealPlan | null>(null);
  const pendingPlan = useRef<PendingPlan | null>(null);
  const [busy, setBusy] = useState(false);
  const busyRef = useRef(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [progress, setProgress] = useState<ProgressSnapshot | null>(null);
  const [progressStatus, setProgressStatus] = useState<AsyncStatus>('idle');
  const [progressError, setProgressError] = useState<string | null>(null);

  const clearSelection = useCallback(() => {
    setSelectedMeal(null); setChoices({}); setPlan(null); pendingPlan.current = null;
    setActionError(null); setNotice(null);
  }, []);
  const loadRecipes = useCallback(async (changes: Partial<Query> = {}) => {
    if (busyRef.current) return;
    const next = { ...queryRef.current, ...changes };
    queryRef.current = next; setQuery(next);
    const token = gate.current.next();
    clearSelection(); setResponse(null); setRecipesError(null); setRecipesStatus('loading');
    try {
      const [nextHealth, result, saved] = await Promise.all([
        api.getHealth(), api.getRecommendations(next.mode, next.anchor, next.storeId), api.getRecipeBook(),
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
    // Starting a new scenario must not inherit the previous locked plan's route.
    setFulfillment(next);
    void loadRecipes({ mode: null, storeId: null });
  };

  const loadProgress = useCallback(async () => {
    const token = progressGate.current.next();
    setProgressStatus('loading'); setProgressError(null);
    try {
      const result = await api.getProgress();
      if (!progressGate.current.isCurrent(token)) return;
      setProgress(result); setProgressStatus('ready');
    } catch (error) {
      if (!progressGate.current.isCurrent(token)) return;
      setProgressError((error as Error).message); setProgressStatus('error');
    }
  }, []);
  const acceptProgress = (value: ProgressSnapshot) => {
    progressGate.current.next(); setProgress(value); setProgressStatus('ready'); setProgressError(null);
  };
  const run = async (operation: () => Promise<void>) => {
    if (busyRef.current) return;
    busyRef.current = true; setBusy(true); setActionError(null); setNotice(null);
    try { await operation(); }
    catch (error) { setActionError((error as Error).message); }
    finally { busyRef.current = false; setBusy(false); }
  };
  const selectMeal = (mealId: string) => {
    if (busyRef.current || recipesStatus !== 'ready') return;
    const meal = response?.recommendations.find((item) => item.meal_id === mealId);
    if (!meal) return;
    clearSelection(); setSelectedMeal(meal); setRoute(meal.default_route); setMarkdown(false);
    const variant = meal.default_route === 'cook' ? meal.cook_variant : meal.ready_variant;
    if (!variant?.fulfillment_options.includes(fulfillment)) {
      setFulfillment(variant?.fulfillment_options[0] ?? 'next_visit');
    }
  };
  const basket = selectedMeal
    ? makeBasket(selectedMeal, route, fulfillment, markdown, choices) : emptyBasket;
  const editable = !busy && !pendingPlan.current;
  const chooseRoute = (next: MealRoute) => {
    if (busyRef.current || pendingPlan.current || !selectedMeal?.available_routes.includes(next)) return;
    setRoute(next); setChoices({}); setActionError(null);
    const variant = next === 'cook' ? selectedMeal.cook_variant : selectedMeal.ready_variant;
    if (!variant?.fulfillment_options.includes(fulfillment)) setFulfillment(variant?.fulfillment_options[0] ?? 'next_visit');
  };
  const chooseFulfillment = (next: FulfillmentOption) => {
    if (busyRef.current || pendingPlan.current) return;
    setFulfillment(next); setChoices({}); setActionError(null);
  };
  const chooseMarkdown = (next: boolean) => {
    if (busyRef.current || pendingPlan.current) return;
    setMarkdown(next); setChoices({}); setActionError(null);
  };
  const chooseProduct = (group: string, skuId: string) => {
    if (busyRef.current || pendingPlan.current) return;
    setChoices((current) => ({ ...current, [group]: skuId })); setActionError(null);
  };
  const saveToBook = () => run(async () => {
    const recipeId = selectedMeal?.cook_variant?.recipe_id;
    if (!recipeId) throw new Error('Для этого предложения нет рецепта для сохранения.');
    const result = await api.saveRecipe(recipeId);
    if (!['created', 'duplicate'].includes(result.status)) throw new Error('Не удалось сохранить рецепт.');
    setBook(result.saved_recipe_ids); setNotice('Рецепт в книге. Его можно выбрать через «Повторить».');
  });
  const savePlan = () => run(async () => {
    if (!selectedMeal) throw new Error('Сначала выберите блюдо.');
    if (!pendingPlan.current) {
      pendingPlan.current = {
        request: makePlan(selectedMeal, route, fulfillment, basket, DEMO_USER_ID,
          `mobile-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`, DEMO_NOW),
        products: basket.products,
      };
    }
    const result = await api.saveMealPlan(pendingPlan.current.request);
    if (!['created', 'duplicate'].includes(result.status) || !result.plan) {
      throw new Error('Сервер отклонил план. Выберите блюдо заново.');
    }
    setPlan(result.plan);
    setNotice('План сохранён. Это список на доставку или визит, не заказ и не бронь.');
  });
  const confirmPurchase = () => run(async () => {
    if (!plan || !pendingPlan.current) throw new Error('Сначала сохраните план.');
    const result = await api.submitReceipt(makeDemoReceipt(
      pendingPlan.current.request, pendingPlan.current.products, DEMO_NOW));
    acceptProgress(result.progress);
    if (result.meal_plan) setPlan(result.meal_plan);
    setNotice(receiptNotice(result));
  });
  const confirmCooking = () => run(async () => {
    if (!plan || (!canCompleteCook(plan) && plan.status !== 'completed')) throw new Error('Сначала соберите продукты.');
    const result = await api.completeCook(plan.plan_id);
    acceptProgress(result.progress);
    if (result.plan) setPlan(result.plan);
    if (!['completed', 'duplicate'].includes(result.status)) throw new Error('Готовка не подтверждена: проверьте план и покупку.');
    setNotice(result.status === 'duplicate' ? 'Блюдо уже учтено; повторных наград нет.' : 'Блюдо приготовлено — прогресс обновлён!');
  });
  return {
    response, health, recipesStatus, recipesError, query, loadRecipes, startEntry, selectedMeal, selectMeal,
    route, chooseRoute, fulfillment, chooseFulfillment, markdown, chooseMarkdown,
    choices, chooseProduct, basket, book, saveToBook, plan, savePlan, editable, busy,
    actionError, notice, confirmPurchase, confirmCooking, progress, progressStatus, progressError, loadProgress,
  };
}
type DemoValue = ReturnType<typeof useDemoState>;
const DemoCtx = createContext<DemoValue | null>(null);
export function DemoProvider({ children }: { children: React.ReactNode }) {
  return <DemoCtx.Provider value={useDemoState()}>{children}</DemoCtx.Provider>;
}
export function useDemo(): DemoValue {
  const value = useContext(DemoCtx);
  if (!value) throw new Error('useDemo вне DemoProvider');
  return value;
}
