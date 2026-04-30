# CVA Matrix Building Examples (.NET Focus)

Complete worked examples of CVA analysis for common .NET scenarios.

## Example 1: Payment Processing (Abstract Factory)

### Phase 1: Identify Commonalities

**Use Cases**:

1. Credit card payment
2. PayPal payment
3. Bank transfer payment

**Commonalities** (ALL cases need):

- Validate payment amount
- Authorize transaction
- Record transaction
- Handle transaction errors

### Phase 2: Identify Variabilities

**Variations by payment method**:

| Commonality | Credit Card | PayPal | Bank Transfer |
|-------------|-------------|--------|---------------|
| How varies? | Card API | PayPal API | ACH API |

### Phase 3: CVA Matrix

| Commonality | Credit Card | PayPal | Bank Transfer |
|-------------|-------------|--------|---------------|
| Validate amount | Check card limit, validate CVV | Check PayPal balance, account status | Check account balance, routing number |
| Authorize transaction | Contact card issuer API | OAuth flow with PayPal | ACH authorization |
| Record transaction | Log to CardTransactionDB | Log to PayPalTransactionDB | Log to BankTransactionDB |
| Handle errors | Card decline codes (51, 05, etc.) | PayPal error codes | ACH rejection codes |

**Analysis**:

- Rows vary across columns (different implementations per method)
- Columns are coherent families (each method has consistent set of operations)
- → **Abstract Factory pattern**

### Phase 4: Pattern Recommendation

**Primary**: Abstract Factory Pattern

**Rationale**: Each payment method (column) requires a coherent family of related operations. Operations are not independent - they share payment method context.

**.NET Implementation**:

```
// Abstract factory interface
public interface IPaymentFactory
{
    IAmountValidator CreateValidator();
    ITransactionAuthorizer CreateAuthorizer();
    ITransactionRecorder CreateRecorder();
    IErrorHandler CreateErrorHandler();
}

// Concrete factory: Credit Card
public class CreditCardPaymentFactory : IPaymentFactory
{
    public IAmountValidator CreateValidator() => new CreditCardValidator();
    public ITransactionAuthorizer CreateAuthorizer() => new CardIssuerAuthorizer();
    public ITransactionRecorder CreateRecorder() => new CardTransactionRecorder();
    public IErrorHandler CreateErrorHandler() => new CardDeclineHandler();
}

// Concrete factory: PayPal
public class PayPalPaymentFactory : IPaymentFactory
{
    public IAmountValidator CreateValidator() => new PayPalBalanceValidator();
    public ITransactionAuthorizer CreateAuthorizer() => new PayPalOAuthAuthorizer();
    public ITransactionRecorder CreateRecorder() => new PayPalTransactionRecorder();
    public IErrorHandler CreateErrorHandler() => new PayPalErrorHandler();
}

// Usage
public class PaymentProcessor
{
    private readonly IPaymentFactory _factory;

    public PaymentProcessor(IPaymentFactory factory)
    {
        _factory = factory;
    }

    public async Task<PaymentResult> ProcessPaymentAsync(PaymentRequest request)
    {
        // All products from same family (cohesive)
        var validator = _factory.CreateValidator();
        var authorizer = _factory.CreateAuthorizer();
        var recorder = _factory.CreateRecorder();
        var errorHandler = _factory.CreateErrorHandler();

        // Workflow uses family of products
        if (!await validator.ValidateAsync(request))
            return errorHandler.HandleValidationError();

        var authResult = await authorizer.AuthorizeAsync(request);
        if (!authResult.IsSuccess)
            return errorHandler.HandleAuthorizationError(authResult);

        await recorder.RecordAsync(authResult);
        return PaymentResult.Success();
    }
}

// DI registration
services.AddScoped<IPaymentFactory>(sp =>
{
    var paymentMethod = GetPaymentMethod();
    return paymentMethod switch
    {
        "CreditCard" => new CreditCardPaymentFactory(),
        "PayPal" => new PayPalPaymentFactory(),
        "BankTransfer" => new BankTransferPaymentFactory(),
        _ => throw new NotSupportedException($"Payment method {paymentMethod} not supported")
    };
});
```

**Alternative Considered**: Strategy pattern per row (4 separate strategies). **Rejected** because operations are not independent - they share payment method context. Keeping them in a factory maintains cohesion.

---

## Example 2: ASP.NET Middleware Pipeline (Abstract Factory)

### CVA Matrix

| Middleware Function | Development | Staging | Production |
|---------------------|-------------|---------|------------|
| Error Handling | Detailed exceptions, stack traces | Log only, generic errors to client | Generic errors, minimal info |
| Authentication | Dev tokens, relaxed validation | Staging AD, moderate validation | Production AD, strict validation |
| Logging | Verbose (all requests) | Moderate (errors + slow) | Minimal (errors only) |
| Compression | Disabled (readability) | Enabled | Enabled |

**Analysis**: Columns are coherent families per environment → **Abstract Factory**

**.NET Implementation**:

```
public interface IEnvironmentMiddlewareFactory
{
    RequestDelegate CreateErrorHandler(RequestDelegate next);
    RequestDelegate CreateAuthMiddleware(RequestDelegate next);
    RequestDelegate CreateLoggingMiddleware(RequestDelegate next);
    RequestDelegate CreateCompressionMiddleware(RequestDelegate next);
}

public class DevelopmentMiddlewareFactory : IEnvironmentMiddlewareFactory
{
    public RequestDelegate CreateErrorHandler(RequestDelegate next) =>
        async context =>
        {
            try { await next(context); }
            catch (Exception ex)
            {
                // Development: detailed exceptions
                context.Response.StatusCode = 500;
                await context.Response.WriteAsync(ex.ToString());
            }
        };

    public RequestDelegate CreateAuthMiddleware(RequestDelegate next) =>
        async context =>
        {
            // Development: relaxed validation
            context.User = CreateDevUserPrincipal();
            await next(context);
        };

    // ... other middleware
}

// Startup configuration
public void Configure(IApplicationBuilder app, IWebHostEnvironment env)
{
    var factory = env.IsDevelopment()
        ? new DevelopmentMiddlewareFactory()
        : env.IsStaging()
            ? new StagingMiddlewareFactory()
            : new ProductionMiddlewareFactory();

    app.Use(factory.CreateErrorHandler);
    app.Use(factory.CreateAuthMiddleware);
    app.Use(factory.CreateLoggingMiddleware);
    app.Use(factory.CreateCompressionMiddleware);
}
```

---

## Example 3: Dependency Injection Lifetime Scopes (Strategy)

### CVA Matrix

| Operation | Transient | Scoped | Singleton |
|-----------|-----------|--------|-----------|
| Create instance | New every request | New per scope | Once per app lifetime |
| Dispose | Immediately after use | End of scope | App shutdown |
| Resolve dependencies | Fresh dependencies | Cached within scope | Cached globally |
| Thread safety | Not required (new each time) | Scope-local only | Must be thread-safe |

**Analysis**: Rows vary independently (each operation has different strategy per lifetime) → **Strategy pattern**

**.NET Implementation**:

```
// Strategy interface
public interface ILifetimeStrategy
{
    object CreateInstance(Type type, IServiceProvider provider);
    void Dispose(object instance);
    object ResolveDependency(Type dependencyType, IServiceProvider provider);
}

// Concrete strategy: Transient
public class TransientLifetimeStrategy : ILifetimeStrategy
{
    public object CreateInstance(Type type, IServiceProvider provider) =>
        Activator.CreateInstance(type);  // New every time

    public void Dispose(object instance)
    {
        if (instance is IDisposable disposable)
            disposable.Dispose();  // Immediately
    }

    public object ResolveDependency(Type dependencyType, IServiceProvider provider) =>
        provider.GetService(dependencyType);  // Fresh
}

// Concrete strategy: Scoped
public class ScopedLifetimeStrategy : ILifetimeStrategy
{
    private readonly Dictionary<Type, object> _scopeCache = new();

    public object CreateInstance(Type type, IServiceProvider provider)
    {
        if (!_scopeCache.TryGetValue(type, out var instance))
        {
            instance = Activator.CreateInstance(type);
            _scopeCache[type] = instance;
        }
        return instance;
    }

    public void Dispose(object instance)
    {
        // Defer until scope ends
    }

    public void EndScope()
    {
        foreach (var instance in _scopeCache.Values.OfType<IDisposable>())
            instance.Dispose();
        _scopeCache.Clear();
    }

    public object ResolveDependency(Type dependencyType, IServiceProvider provider) =>
        _scopeCache.TryGetValue(dependencyType, out var cached)
            ? cached  // Cached within scope
            : provider.GetService(dependencyType);
}

// Concrete strategy: Singleton
public class SingletonLifetimeStrategy : ILifetimeStrategy
{
    private static readonly ConcurrentDictionary<Type, Lazy<object>> _instances = new();

    public object CreateInstance(Type type, IServiceProvider provider) =>
        _instances.GetOrAdd(type, t => new Lazy<object>(() => Activator.CreateInstance(t))).Value;

    public void Dispose(object instance)
    {
        // Never dispose (app lifetime)
    }

    public object ResolveDependency(Type dependencyType, IServiceProvider provider) =>
        CreateInstance(dependencyType, provider);  // Globally cached
}

// Usage
public class ServiceDescriptor
{
    public Type ServiceType { get; }
    public ILifetimeStrategy LifetimeStrategy { get; }

    public ServiceDescriptor(Type serviceType, ServiceLifetime lifetime)
    {
        ServiceType = serviceType;
        LifetimeStrategy = lifetime switch
        {
            ServiceLifetime.Transient => new TransientLifetimeStrategy(),
            ServiceLifetime.Scoped => new ScopedLifetimeStrategy(),
            ServiceLifetime.Singleton => new SingletonLifetimeStrategy(),
            _ => throw new ArgumentException(nameof(lifetime))
        };
    }

    public object Resolve(IServiceProvider provider) =>
        LifetimeStrategy.CreateInstance(ServiceType, provider);
}
```

---

## When NOT to Abstract (YAGNI Examples)

### Example: Single Payment Method (No Variability)

**Matrix**:

| Commonality | Credit Card |
|-------------|-------------|
| Validate    | Card limit  |
| Authorize   | Issuer API  |
| Record      | CardDB      |
| Handle      | Decline codes |

**Analysis**: Only 1 column (no variability to abstract over)

**Decision**: **Don't abstract**. Wait for 2nd payment method per YAGNI.

**Implementation**: Concrete class, no interfaces

```
public class CreditCardPaymentProcessor
{
    public async Task<PaymentResult> ProcessAsync(PaymentRequest request)
    {
        // Concrete implementation
        // No abstraction overhead
    }
}
```

**ADR Stub**:

```
# ADR-XXX: No Abstraction for Payment Processing

## Context
Only 1 payment method (Credit Card) currently supported.

## Decision
Use concrete `CreditCardPaymentProcessor` class. No abstraction.

## Rationale
- CVA matrix shows no variability (1 column)
- YAGNI: Don't abstract until 2+ payment methods exist
- Premature abstraction worse than no abstraction (CLAUDE.md)

## Reassessment Trigger
When 2nd payment method (PayPal, Bank Transfer) is added, re-run CVA and abstract.
```

---

## Edge Case: All Variability (Reconsider Scope)

**Matrix**:

| Commonality | Use Case 1 | Use Case 2 | Use Case 3 |
|-------------|------------|------------|------------|
| Workflow    | A → B → C  | X → Y → Z  | M → N → O  |
| Data        | Type1      | Type2      | Type3      |
| Output      | Format1    | Format2    | Format3    |

**Analysis**: Every cell different (no commonality)

**Decision**: **Reconsider scope**. Use cases may be unrelated. Analyze separately or narrow scope.

---

## Reassessment Triggers

Re-run CVA when:

1. **3+ new use cases** added
2. **Major architectural shift** (monolith → microservices)
3. **Performance issues** (abstraction overhead not justified)
4. **Team feedback** (abstraction too complex or not pulling weight)
5. **Quarterly review** (align with retrospective cycle)

---

## Further Reading

- **Pattern Mapping Guide**: `pattern-mapping-guide.md`
- **Multidimensional CVA**: `multidimensional-cva.md`
- **Coplien Papers**: `coplien-multi-paradigm-design.md`
