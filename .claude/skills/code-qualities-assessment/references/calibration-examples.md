# Calibration Examples

Reference examples for consistent code quality scoring across teams.

## Cohesion Examples

### Score: 10/10 (Perfect Cohesion)

```python
class EmailValidator:
    """Single responsibility: validate email addresses"""

    def validate(self, email: str) -> bool:
        return self._has_valid_format(email) and self._has_valid_domain(email)

    def _has_valid_format(self, email: str) -> bool:
        return "@" in email and "." in email.split("@")[1]

    def _has_valid_domain(self, email: str) -> bool:
        domain = email.split("@")[1]
        return len(domain) > 3
```

**Why 10**: Every method serves email validation. All methods use same data. Clear single purpose.

### Score: 7/10 (Good Cohesion)

```python
class User:
    """Represents a user with validation"""

    def __init__(self, email: str, name: str):
        self.email = email
        self.name = name
        self.created_at = datetime.now()  # Minor supporting concern

    def validate(self) -> bool:
        return self._validate_email() and self._validate_name()

    def _validate_email(self) -> bool:
        return "@" in self.email

    def _validate_name(self) -> bool:
        return len(self.name) > 0
```

**Why 7**: Primary responsibility (user data) is clear. Validation is closely related. Timestamp is minor but justified.

### Score: 4/10 (Weak Cohesion)

```python
class UserManager:
    """Mixed responsibilities"""

    def create_user(self, email: str) -> User:
        return User(email)

    def send_email(self, to: str, subject: str) -> None:
        # Email sending logic
        pass

    def log_activity(self, message: str) -> None:
        # Logging logic
        pass
```

**Why 4**: Three unrelated responsibilities (user creation, email, logging). Name is vague ("Manager").

### Score: 1/10 (No Cohesion)

```python
class Utilities:
    """God object with random utilities"""

    def format_date(self, date: datetime) -> str:
        pass

    def calculate_tax(self, amount: float) -> float:
        pass

    def send_sms(self, phone: str, message: str) -> None:
        pass

    def hash_password(self, password: str) -> str:
        pass
```

**Why 1**: Completely unrelated functions. Impossible to describe in one sentence.

---

## Coupling Examples

### Score: 10/10 (Minimal Coupling)

```python
class OrderProcessor:
    def __init__(self, payment_service: PaymentServiceInterface):
        self._payment_service = payment_service  # Injected dependency

    def process(self, order: Order) -> bool:
        return self._payment_service.charge(order.total)
```

**Why 10**: Depends on interface, not implementation. Easy to test with mocks. No global state.

### Score: 7/10 (Loose Coupling)

```python
class OrderProcessor:
    def __init__(self):
        self._payment_service = PaymentService()  # Direct instantiation

    def process(self, order: Order) -> bool:
        return self._payment_service.charge(order.total)
```

**Why 7**: Direct instantiation creates coupling, but isolated to constructor. Still testable.

### Score: 4/10 (Moderate Coupling)

```python
class OrderProcessor:
    def process(self, order: Order) -> bool:
        # Global singleton access
        payment = PaymentService.get_instance()
        logger = Logger.get_instance()

        logger.info("Processing order")
        return payment.charge(order.total)
```

**Why 4**: Depends on singletons (hidden dependencies). Global state. Hard to test.

### Score: 1/10 (Tight Coupling)

```python
class OrderProcessor:
    def process(self, order: Order) -> bool:
        # Hard-coded dependencies everywhere
        db = DatabaseConnection("localhost", 5432)
        payment = StripePayment(api_key="sk_live_...")
        email = SmtpEmail("smtp.gmail.com")

        db.save(order)
        payment.charge(order.total)
        email.send(order.user.email, "Order confirmed")
        return True
```

**Why 1**: Hard-coded connections. Impossible to test without real Stripe, SMTP, DB.

---

## Encapsulation Examples

### Score: 10/10 (Perfect Encapsulation)

```python
class BankAccount:
    def __init__(self, initial_balance: float):
        self.__balance = initial_balance  # Private field

    def deposit(self, amount: float) -> None:
        if amount > 0:
            self.__balance += amount

    def get_balance(self) -> float:
        return self.__balance  # Returns value, not reference
```

**Why 10**: All internals private. Minimal public API. Balance cannot be modified directly.

### Score: 7/10 (Good Encapsulation)

```python
class BankAccount:
    def __init__(self, initial_balance: float):
        self._balance = initial_balance  # Protected (convention)

    def deposit(self, amount: float) -> None:
        self._balance += amount

    @property
    def balance(self) -> float:
        return self._balance
```

**Why 7**: Uses properties for controlled access. Balance is protected (not private). Good enough for most cases.

### Score: 4/10 (Weak Encapsulation)

```python
class BankAccount:
    def __init__(self, initial_balance: float):
        self.balance = initial_balance  # Public field
        self.transactions = []  # Public mutable list

    def deposit(self, amount: float) -> None:
        self.balance += amount
        self.transactions.append(amount)
```

**Why 4**: Public fields allow direct modification. Mutable list can be modified externally.

### Score: 1/10 (No Encapsulation)

```python
class BankAccount:
    balance = 0  # Class variable (shared)
    transactions = []  # Shared mutable list

    def __init__(self, initial_balance: float):
        BankAccount.balance = initial_balance
```

**Why 1**: Everything is public and shared. Massive coupling. Bugs guaranteed.

---

## Testability Examples

### Score: 10/10 (Perfect Testability)

```python
def calculate_discount(price: float, discount_rate: float) -> float:
    """Pure function - no side effects, deterministic"""
    return price * (1 - discount_rate)

# Test
assert calculate_discount(100, 0.2) == 80
```

**Why 10**: Pure function. No dependencies. No side effects. Trivial to test.

### Score: 7/10 (Good Testability)

```python
class DiscountCalculator:
    def __init__(self, tax_rate: float):
        self.tax_rate = tax_rate

    def calculate_final_price(self, price: float, discount: float) -> float:
        discounted = price * (1 - discount)
        return discounted * (1 + self.tax_rate)

# Test
calc = DiscountCalculator(tax_rate=0.1)
assert calc.calculate_final_price(100, 0.2) == 88
```

**Why 7**: Deterministic. Dependencies injected. Easy to set up tests.

### Score: 4/10 (Moderate Testability)

```python
class DiscountCalculator:
    def calculate_final_price(self, price: float, discount: float) -> float:
        tax_rate = self._get_tax_rate_from_db()  # Database call
        discounted = price * (1 - discount)
        return discounted * (1 + tax_rate)

    def _get_tax_rate_from_db(self) -> float:
        # Database query
        pass

# Test requires mocking database
```

**Why 4**: Requires mocking. Not deterministic. Setup is complex.

### Score: 1/10 (Hard to Test)

```python
import random
from datetime import datetime

class DiscountCalculator:
    def calculate_final_price(self, price: float) -> float:
        # Non-deterministic
        random_discount = random.random()

        # Global state
        global CURRENT_TAX_RATE

        # Time-dependent
        if datetime.now().hour < 12:
            extra_discount = 0.1
        else:
            extra_discount = 0

        return price * (1 - random_discount - extra_discount) * (1 + CURRENT_TAX_RATE)
```

**Why 1**: Non-deterministic (random). Global state. Time-dependent. Untestable without full integration.

---

## Non-Redundancy Examples

### Score: 10/10 (Zero Duplication)

```python
def calculate_tax(amount: float, rate: float) -> float:
    return amount * rate

def calculate_order_total(subtotal: float, tax_rate: float) -> float:
    return subtotal + calculate_tax(subtotal, tax_rate)

def calculate_invoice_total(subtotal: float, tax_rate: float) -> float:
    return subtotal + calculate_tax(subtotal, tax_rate)
```

**Why 10**: Tax calculation abstracted. Reused in both functions. Single source of truth.

### Score: 7/10 (Minimal Duplication)

```python
def calculate_order_total(subtotal: float, tax_rate: float) -> float:
    tax = subtotal * tax_rate
    return subtotal + tax

def calculate_invoice_total(subtotal: float, tax_rate: float, discount: float) -> float:
    discounted = subtotal * (1 - discount)
    tax = discounted * tax_rate  # Intentional duplication for clarity
    return discounted + tax
```

**Why 7**: Minor duplication of tax calculation. Justified by different contexts.

### Score: 4/10 (Moderate Duplication)

```python
def process_order(subtotal: float, tax_rate: float) -> float:
    tax = subtotal * tax_rate
    shipping = 10.0
    total = subtotal + tax + shipping
    print(f"Order: ${total:.2f}")
    return total

def process_invoice(subtotal: float, tax_rate: float) -> float:
    tax = subtotal * tax_rate  # Duplicated
    shipping = 10.0  # Duplicated
    total = subtotal + tax + shipping  # Duplicated
    print(f"Invoice: ${total:.2f}")  # Similar
    return total
```

**Why 4**: Significant duplication. Missed abstraction opportunity.

### Score: 1/10 (Pervasive Duplication)

```python
def process_order(subtotal: float, tax_rate: float) -> float:
    tax = subtotal * tax_rate
    shipping = 10.0
    handling = 5.0
    total = subtotal + tax + shipping + handling
    if total > 100:
        total *= 0.9
    print(f"Order total: ${total:.2f}")
    return total

def process_invoice(subtotal: float, tax_rate: float) -> float:
    tax = subtotal * tax_rate
    shipping = 10.0
    handling = 5.0
    total = subtotal + tax + shipping + handling
    if total > 100:
        total *= 0.9
    print(f"Invoice total: ${total:.2f}")
    return total

def process_quote(subtotal: float, tax_rate: float) -> float:
    tax = subtotal * tax_rate
    shipping = 10.0
    handling = 5.0
    total = subtotal + tax + shipping + handling
    if total > 100:
        total *= 0.9
    print(f"Quote total: ${total:.2f}")
    return total
```

**Why 1**: Copy-paste everywhere. Fixing bugs requires updating 3 places. Nightmare.

---

## Language-Specific Adaptations

### Python: Duck Typing Encapsulation

```python
class Example:
    def __init__(self):
        self._private = "use single underscore"  # Convention
        self.__really_private = "double underscore mangles name"  # Rare
```

Score based on convention adherence, not enforcement.

### TypeScript: Interface Segregation

```typescript
// Good coupling (10/10)
interface PaymentProcessor {
  charge(amount: number): Promise<boolean>;
}

class Order {
  constructor(private payment: PaymentProcessor) {}
}

// Poor coupling (4/10)
class Order {
  constructor(private payment: StripePayment) {}  // Concrete dependency
}
```

### C#: Property Encapsulation

```csharp
// Perfect encapsulation (10/10)
public class BankAccount
{
    private decimal _balance;

    public decimal Balance => _balance;  // Read-only property

    public void Deposit(decimal amount) => _balance += amount;
}

// Weak encapsulation (4/10)
public class BankAccount
{
    public decimal Balance { get; set; }  // Public setter
}
```

---

## Calibration Workshop

Use these examples in team calibration sessions:

1. **Round 1**: Score examples independently
2. **Round 2**: Compare scores, discuss differences
3. **Round 3**: Reach consensus on borderline cases
4. **Round 4**: Create team-specific examples

**Goal**: 80%+ agreement on scores within ±1 point.
