# Taking payments: options (not built yet)

Written 23 Nov 2026. Fees and API rules change, so check current terms before choosing.

Two different jobs:
- **A. HapiTech gets paid by clients:** website work, add-ons, any balance. The client sees a balance in their dashboard and pays it.
- **B. Clients get paid by their customers:** Roland's own invoices to his customers. Each client would connect their own account. Later, and only if they want it.

## Options for A

| # | How | Client experience | Automation | Needs |
|---|---|---|---|---|
| 1 | **Bank transfer + reference** (what we do now) | Dashboard shows the amount, your bank details and a reference like `HT-0042` | Aaron marks it paid | Nothing. Free |
| 2 | **Revolut Business: Merchant API** (payment links / Revolut Checkout) | "Pay now" opens a Revolut-hosted card / Apple Pay / Google Pay / Revolut Pay page | We create a payment link per invoice; a **webhook marks it paid** automatically | Merchant account switched on in Revolut Business, plus an API key. Card fees per transaction |
| 3 | **PayPal Checkout** (Orders API + webhook) | "Pay with PayPal" button; they can also pay by card through PayPal without an account | Webhook marks it paid | PayPal developer app (client ID + secret) on your business account. PayPal fees, usually higher than Revolut for UK cards |
| 4 | **PayPal.me / Revolut.me link** | Fixed link, they type the amount | None; Aaron matches payments by hand | Nothing. Quick stopgap only |
| 5 | **Direct Debit** (GoCardless, or Stripe Bacs) | Set up once; monthly fees come out automatically | Fully automatic for recurring plans | A new account with that provider. Best for monthly upkeep later; not needed while everyone is on the Friends plan |

**Recommendation:** start with **1 + 2**:
- Show the balance and bank details with a reference (free).
- Add a **"Pay by card"** button through Revolut (lower fees, an account you already have), with automatic "paid" via webhook.
- Add PayPal (3) as a second button only if a client asks for it.
- Look at Direct Debit (5) only if monthly charging starts.

Built on what we have: admin already records **Payments** and **Subscriptions** per client.
- Add a client-facing **"Balance"** card (dashboard Home, plus a Billing section in Settings) listing what's due, each with "Pay by card" and the bank details.
- Payment confirmations go to Aaron and to the client, using the styled emails.
- No card details ever touch our server: Revolut and PayPal host the payment page.

## For B (later)
- Easiest: let each client paste their own **PayPal.me / Revolut.me / bank details**, shown as "How to pay" on their invoices. Part of this already exists in Settings, as "How customers pay you".
- Proper "Pay now" on customer invoices would need each client's own merchant account connected. That's only worth it if they ask.

## Before building, Aaron to decide
1. Revolut merchant account: is it already active? If not, switch it on in Revolut Business → Merchant.
2. Which charges go through the dashboard: one-off website work, or monthly plans later too?
3. Should a balance show only when you've added a charge, or always (with "Nothing due ✓")?
