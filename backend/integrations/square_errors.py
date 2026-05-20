"""Square error sanitization — maps raw Square exceptions to user-friendly messages."""


SAFE_MESSAGES = {
    "CARD_DECLINED":                "Your card was declined. Please try a different card.",
    "INVALID_CARD":                 "Card details are invalid.",
    "INVALID_CARD_DATA":            "Card details are invalid.",
    "INVALID_EXPIRATION":           "Card expiration date is invalid.",
    "VERIFY_CVV_FAILURE":           "Card CVV check failed.",
    "VERIFY_AVS_FAILURE":           "Billing address verification failed.",
    "EXPIRED_CARD":                 "Card is expired.",
    "INSUFFICIENT_FUNDS":           "Insufficient funds on the card.",
    "CARD_TOKEN_USED":              "This card token has already been used. Please retry.",
    "CARD_TOKEN_EXPIRED":           "Card token expired. Please re-enter card details.",
    "BAD_REQUEST":                  "Subscription request was rejected. Please try again.",
    "UNAUTHORIZED":                 "Payment provider unavailable. Try again later.",
}


def sanitize_square_error(exc: Exception) -> str:
    """Return a safe, user-friendly error string. Never leak raw Square text."""
    raw = str(exc) if exc else ""
    # Look for a Square error code token in the raw text
    upper = raw.upper()
    for code, msg in SAFE_MESSAGES.items():
        if code in upper:
            return msg
    if "PLAN_VARIATION" in upper or "PLAN" in upper and "NOT" in upper:
        return "Subscription plan not configured. Contact support."
    if "CUSTOMER" in upper and "NOT" in upper:
        return "Could not create customer record. Please retry."
    return "Payment processing failed. Please try again."
