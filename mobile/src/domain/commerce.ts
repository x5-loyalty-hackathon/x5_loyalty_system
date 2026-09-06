import type { PlanRequest, ProductOption } from '../api/types.ts';
import type { DemoReceiptEvent } from './mealFlow.ts';
import { makeDemoReceipt } from './mealFlow.ts';
import { DEMO_NOW } from '../fixtures/recommendationRequest.ts';

/** Host grocery app owns cart/address/checkout UI. No payment screen in the game. */
export interface CheckoutRequest {
  /** Stable idempotency key: retry must resume this checkout, not place another order. */
  checkoutId: string;
  plan: PlanRequest;
  products: ProductOption[];
}
export type CheckoutResult = { status: 'cancelled' } | {
  status: 'purchased'; receipt: DemoReceiptEvent;
};
export interface CommerceHost {
  /** Explicitly marks simulation in the UI; omitted means an external host. */
  readonly mode?: 'demo' | 'external';
  /** External hosts resolve after purchase evidence, not payment intent.
   * Demo hosts explicitly model that external purchase instead. */
  openCheckout(request: CheckoutRequest): Promise<CheckoutResult>;
}

/** Standalone hackathon default: model the external purchase, not XP or API results.
 * No network/payment here. The event still goes through the real receipt endpoint.
 * Fixed demo time + plan ID make retries stable, without minting another day.
 */
export const demoCommerceHost: CommerceHost = {
  mode: 'demo',
  async openCheckout({ checkoutId, plan, products }) {
    if (checkoutId !== plan.plan_id) throw new Error('Попытка оформления не совпадает с заданием.');
    return { status: 'purchased', receipt: makeDemoReceipt(plan, products, DEMO_NOW) };
  },
};

// Native can pass a host to DemoProvider; web can install one before mounting.
// An explicitly configured host is never replaced with a simulated success on error.
declare global { var __X5_COMMERCE_HOST__: CommerceHost | undefined; }
export function getCommerceHost(): CommerceHost {
  return globalThis.__X5_COMMERCE_HOST__ ?? demoCommerceHost;
}
