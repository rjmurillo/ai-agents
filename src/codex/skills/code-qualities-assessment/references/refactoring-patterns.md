# Refactoring Patterns for Code Quality

Remediation patterns for low quality scores.

## Low Cohesion → Extract Class

**Pattern**: When a class has multiple unrelated responsibilities, split it.

### Before (Score: 4/10)

```
class UserManager:
    def create_user(self, email: str) -> User:
        user = User(email)
        self._save_to_database(user)
        return user

    def send_welcome_email(self, user: User) -> None:
        # Email logic
        pass

    def log_activity(self, message: str) -> None:
        # Logging logic
        pass

    def _save_to_database(self, user: User) -> None:
        # Database logic
        pass
```

### After (Score: 9/10)

```
class UserRepository:
    """Single responsibility: user persistence"""
    def save(self, user: User) -> None:
        # Database logic
        pass

class EmailService:
    """Single responsibility: email sending"""
    def send_welcome(self, user: User) -> None:
        # Email logic
        pass

class ActivityLogger:
    """Single responsibility: logging"""
    def log(self, message: str) -> None:
        # Logging logic
        pass

class UserService:
    """Orchestrates user creation (sergeant method)"""
    def __init__(self, repo: UserRepository, email: EmailService, logger: ActivityLogger):
        self._repo = repo
        self._email = email
        self._logger = logger

    def create_user(self, email_address: str) -> User:
        user = User(email_address)
        self._repo.save(user)
        self._email.send_welcome(user)
        self._logger.log(f"Created user: {email_address}")
        return user
```

**Quality improvement**:

- Cohesion: 4 → 9 (each class has single responsibility)
- Testability: 4 → 9 (easy to mock dependencies)
- Coupling: 5 → 8 (dependencies injected)

---

## High Coupling → Dependency Injection

**Pattern**: Replace hard-coded dependencies with injected abstractions.

### Before (Score: 3/10)

```
class OrderProcessor:
    def process(self, order: Order) -> bool:
        # Hard-coded dependencies
        payment = StripePayment(api_key="sk_live_...")
        email = SmtpEmail("smtp.gmail.com")

        if payment.charge(order.total):
            email.send(order.user.email, "Order confirmed")
            return True
        return False
```

### After (Score: 9/10)

```
from typing import Protocol

class PaymentProcessor(Protocol):
    def charge(self, amount: float) -> bool: ...

class EmailSender(Protocol):
    def send(self, to: str, subject: str) -> None: ...

class OrderProcessor:
    def __init__(self, payment: PaymentProcessor, email: EmailSender):
        self._payment = payment
        self._email = email

    def process(self, order: Order) -> bool:
        if self._payment.charge(order.total):
            self._email.send(order.user.email, "Order confirmed")
            return True
        return False

# Easy to test with mocks
class MockPayment:
    def charge(self, amount: float) -> bool:
        return True

processor = OrderProcessor(MockPayment(), MockEmail())
```

**Quality improvement**:

- Coupling: 3 → 9 (depends on abstractions)
- Testability: 2 → 10 (trivial to mock)

---

## Poor Encapsulation → Facade Pattern

**Pattern**: Hide complex internals behind a simple interface.

### Before (Score: 4/10)

```
class PaymentSystem:
    # Too many public methods exposing internals
    def validate_card(self, card: Card) -> bool: ...
    def check_fraud(self, transaction: Transaction) -> bool: ...
    def call_gateway(self, data: dict) -> Response: ...
    def save_transaction(self, transaction: Transaction) -> None: ...
    def send_receipt(self, email: str, transaction: Transaction) -> None: ...
```

### After (Score: 9/10)

```
class PaymentSystem:
    def charge(self, card: Card, amount: float, email: str) -> bool:
        """Simple public API - internals are private"""
        if not self._validate_card(card):
            return False

        transaction = self._create_transaction(card, amount)

        if not self._check_fraud(transaction):
            return False

        if self._call_gateway(transaction):
            self._save_transaction(transaction)
            self._send_receipt(email, transaction)
            return True

        return False

    # All implementation details are private
    def _validate_card(self, card: Card) -> bool: ...
    def _check_fraud(self, transaction: Transaction) -> bool: ...
    def _call_gateway(self, transaction: Transaction) -> bool: ...
    def _save_transaction(self, transaction: Transaction) -> None: ...
    def _send_receipt(self, email: str, transaction: Transaction) -> None: ...
```

**Quality improvement**:

- Encapsulation: 4 → 9 (1 public method, internals hidden)
- Cohesion: 6 → 8 (clear orchestration)

---

## Low Testability → Dependency Inversion

**Pattern**: Invert dependencies to make code testable.

### Before (Score: 2/10)

```
import random
from datetime import datetime

class DiscountCalculator:
    def calculate(self, price: float) -> float:
        # Non-deterministic
        random_factor = random.random()

        # Global state
        global TAX_RATE

        # Time-dependent
        if datetime.now().hour < 12:
            return price * 0.9 * random_factor * (1 + TAX_RATE)
        return price * random_factor * (1 + TAX_RATE)
```

### After (Score: 9/10)

```
from datetime import datetime
from typing import Protocol

class RandomGenerator(Protocol):
    def generate(self) -> float: ...

class TimeProvider(Protocol):
    def current_hour(self) -> int: ...

class TaxRateProvider(Protocol):
    def get_rate(self) -> float: ...

class DiscountCalculator:
    def __init__(
        self,
        random_gen: RandomGenerator,
        time_provider: TimeProvider,
        tax_provider: TaxRateProvider
    ):
        self._random = random_gen
        self._time = time_provider
        self._tax = tax_provider

    def calculate(self, price: float) -> float:
        random_factor = self._random.generate()
        tax_rate = self._tax.get_rate()

        if self._time.current_hour() < 12:
            return price * 0.9 * random_factor * (1 + tax_rate)
        return price * random_factor * (1 + tax_rate)

# Now testable!
class FixedRandom:
    def generate(self) -> float:
        return 0.5

class FixedTime:
    def __init__(self, hour: int):
        self.hour = hour

    def current_hour(self) -> int:
        return self.hour

class FixedTax:
    def get_rate(self) -> float:
        return 0.1

calc = DiscountCalculator(FixedRandom(), FixedTime(10), FixedTax())
assert calc.calculate(100) == 49.5  # Deterministic!
```

**Quality improvement**:

- Testability: 2 → 9 (fully deterministic)
- Coupling: 4 → 8 (dependencies injected)

---

## High Duplication → Extract Function

**Pattern**: Replace copy-pasted code with shared abstraction.

### Before (Score: 2/10)

```
def calculate_order_total(subtotal: float, tax_rate: float) -> float:
    tax = subtotal * tax_rate
    shipping = 10.0
    handling = 5.0
    total = subtotal + tax + shipping + handling
    if total > 100:
        total *= 0.9
    return total

def calculate_invoice_total(subtotal: float, tax_rate: float) -> float:
    tax = subtotal * tax_rate  # Duplicated
    shipping = 10.0  # Duplicated
    handling = 5.0  # Duplicated
    total = subtotal + tax + shipping + handling  # Duplicated
    if total > 100:  # Duplicated
        total *= 0.9  # Duplicated
    return total

def calculate_quote_total(subtotal: float, tax_rate: float) -> float:
    tax = subtotal * tax_rate  # Duplicated
    shipping = 10.0  # Duplicated
    handling = 5.0  # Duplicated
    total = subtotal + tax + shipping + handling  # Duplicated
    if total > 100:  # Duplicated
        total *= 0.9  # Duplicated
    return total
```

### After (Score: 10/10)

```
SHIPPING_FEE = 10.0
HANDLING_FEE = 5.0
BULK_DISCOUNT_THRESHOLD = 100.0
BULK_DISCOUNT_RATE = 0.9

def calculate_total(subtotal: float, tax_rate: float) -> float:
    """Single source of truth for total calculation"""
    tax = subtotal * tax_rate
    total = subtotal + tax + SHIPPING_FEE + HANDLING_FEE

    if total > BULK_DISCOUNT_THRESHOLD:
        total *= BULK_DISCOUNT_RATE

    return total

def calculate_order_total(subtotal: float, tax_rate: float) -> float:
    return calculate_total(subtotal, tax_rate)

def calculate_invoice_total(subtotal: float, tax_rate: float) -> float:
    return calculate_total(subtotal, tax_rate)

def calculate_quote_total(subtotal: float, tax_rate: float) -> float:
    return calculate_total(subtotal, tax_rate)
```

**Quality improvement**:

- Non-redundancy: 2 → 10 (zero duplication)
- Testability: 6 → 9 (test once, applies everywhere)

---

## Programming by Intention Pattern

**Sergeant methods** direct **private methods**.

### Before (Mixed Abstraction Levels)

```
def process_order(order: Order) -> bool:
    # Low-level details mixed with high-level orchestration
    if not order.email or "@" not in order.email:
        return False

    db_conn = psycopg2.connect("host=localhost dbname=orders")
    cursor = db_conn.cursor()
    cursor.execute("INSERT INTO orders VALUES (%s, %s)", (order.id, order.total))
    db_conn.commit()
    db_conn.close()

    smtp = smtplib.SMTP("smtp.gmail.com")
    smtp.sendmail("noreply@example.com", order.email, "Order confirmed")
    smtp.quit()

    return True
```

### After (Sergeant + Privates)

```
def process_order(order: Order) -> bool:
    """Sergeant method: high-level orchestration"""
    if not self._is_valid_order(order):
        return False

    self._save_order(order)
    self._send_confirmation(order)
    return True

def _is_valid_order(self, order: Order) -> bool:
    """Private: focused validation logic"""
    return order.email and "@" in order.email

def _save_order(self, order: Order) -> None:
    """Private: focused persistence logic"""
    db_conn = self._get_db_connection()
    cursor = db_conn.cursor()
    cursor.execute("INSERT INTO orders VALUES (%s, %s)", (order.id, order.total))
    db_conn.commit()
    db_conn.close()

def _send_confirmation(self, order: Order) -> None:
    """Private: focused email logic"""
    smtp = self._get_smtp_connection()
    smtp.sendmail("noreply@example.com", order.email, "Order confirmed")
    smtp.quit()
```

**Quality improvement**:

- Cohesion: 5 → 9 (each method has single focus)
- Testability: 4 → 8 (can test parts separately)
- Readability: Massively improved

---

## Quick Reference

| Low Score In | Use Pattern | Improvement |
|--------------|-------------|-------------|
| Cohesion | Extract Class | Split responsibilities |
| Coupling | Dependency Injection | Inject abstractions |
| Encapsulation | Facade | Hide internals |
| Testability | Dependency Inversion | Make deterministic |
| Non-redundancy | Extract Function | Share common code |

---

## Related Resources

- Fowler's Refactoring Catalog: <https://refactoring.com/catalog/>
- Martin's Clean Code: SOLID principles
- Evans' DDD: Bounded contexts, aggregates
