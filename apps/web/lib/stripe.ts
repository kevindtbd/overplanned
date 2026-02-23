import Stripe from "stripe";

const globalForStripe = globalThis as unknown as { stripe?: Stripe };

export const stripe =
  globalForStripe.stripe ??
  new Stripe(process.env.STRIPE_SECRET_KEY!, {
    apiVersion: "2024-06-20",
    typescript: true,
  });

if (process.env.NODE_ENV !== "production") globalForStripe.stripe = stripe;
