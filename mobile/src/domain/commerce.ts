import type { PlanRequest, ProductOption } from '../api/types.ts';
import type { DemoReceiptEvent } from './mealFlow.ts';

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
  /** Resolve purchased only after purchase evidence, never on opening/payment intent. */
  openCheckout(request: CheckoutRequest): Promise<CheckoutResult>;
}

// A native host supplies the adapter to DemoProvider. A web host may install it
// before use; the standalone bundle deliberately does not fabricate a purchase.
declare global { var __X5_COMMERCE_HOST__: CommerceHost | undefined; }
export function getCommerceHost(): CommerceHost {
  const host = globalThis.__X5_COMMERCE_HOST__;
  if (!host?.openCheckout) throw new Error(
    'Оформление открывается в приложении магазина. В автономном демо оно не подключено.',
  );
  return host;
}
