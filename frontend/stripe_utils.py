import stripe
import os

stripe.api_key = os.getenv("STRIPE_SECRET_KEY")
DOMAIN = "https://datumsync.onrender.com"  # update if local

def create_checkout_session(customer_email: str):
    try:
        session = stripe.checkout.Session.create(
            payment_method_types=["card"],
            customer_email=customer_email,
            line_items=[{
                'price': 'price_1Rc2PuQlFrpjSznz6JABymPm',  # Replace with your actual Stripe Price ID
                'quantity': 1,
            }],
            mode='subscription',
            success_url=f"{DOMAIN}/subscription/success",
            cancel_url=f"{DOMAIN}/subscription/cancel",
        )
        return session.url
    except Exception as e:
        print("❌ Stripe error:", e)
        return None
