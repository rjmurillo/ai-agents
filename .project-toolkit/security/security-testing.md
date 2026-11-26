# Security Testing Reference

<!-- doc-accuracy: external-sdk xUnit -- C# examples use xUnit and ASP.NET Core test hosting, not this repository -->

This reference contains section 5 from the [Security Best Practices Enforcement Guide](./security-best-practices.md).
It preserves the section's coverage targets, required security test examples, and checklist.

## 5. Testing Requirements

### Security Testing Coverage

| Code Area | Coverage Target | Test Types |
|-----------|-----------------|------------|
| Authentication | 95% | Unit + Integration |
| Authorization | 95% | Unit + Integration |
| Input validation | 90% | Unit + Fuzzing |
| Cryptography | 95% | Unit |
| Error handling | 85% | Unit + Integration |
| Security middleware | 90% | Integration |

### Required Security Tests

#### Authentication Tests

Derive a test class with an isolated application client for each test.
Seed the active and locked accounts below and allow five failed attempts per account.

```csharp
using System.Net;
using System.Net.Http;
using System.Net.Http.Json;
using System.Threading.Tasks;
using Xunit;

public abstract class AuthenticationTests(HttpClient client)
{
    private const string ActiveAccount = "active@example.test";
    private const string TestPassword = "local-fixture-password";

    [Fact]
    public async Task Login_ValidCredentials_ReturnsToken()
    {
        using var response = await Login(ActiveAccount, TestPassword);
        Assert.Equal(HttpStatusCode.OK, response.StatusCode);
        var token = await response.Content.ReadFromJsonAsync<LoginResponse>();
        Assert.False(string.IsNullOrWhiteSpace(token?.AccessToken));
    }

    [Fact]
    public async Task Login_InvalidPassword_ReturnsUnauthorized()
    {
        using var response = await Login(ActiveAccount, "incorrect");
        Assert.Equal(HttpStatusCode.Unauthorized, response.StatusCode);
    }

    [Fact]
    public async Task Login_NonexistentUser_ReturnsSameResponseAsInvalidPassword()
    {
        using var missing = await Login("missing@example.test", TestPassword);
        using var invalid = await Login(ActiveAccount, "incorrect");
        Assert.Equal(HttpStatusCode.Unauthorized, missing.StatusCode);
        Assert.Equal(invalid.StatusCode, missing.StatusCode);
        Assert.Equal(await invalid.Content.ReadAsStringAsync(), await missing.Content.ReadAsStringAsync());
    }

    [Fact]
    public async Task Login_LockedAccount_DeniesValidCredentials()
    {
        using var response = await Login("locked@example.test", TestPassword);
        Assert.Equal(HttpStatusCode.Unauthorized, response.StatusCode);
    }

    [Fact]
    public async Task Login_BruteForce_RateLimits()
    {
        for (int attempt = 0; attempt < 5; attempt++)
        {
            using var failure = await Login(ActiveAccount, "incorrect");
            Assert.Equal(HttpStatusCode.Unauthorized, failure.StatusCode);
        }

        using var limited = await Login(ActiveAccount, "incorrect");
        Assert.Equal(HttpStatusCode.TooManyRequests, limited.StatusCode);
    }

    private Task<HttpResponseMessage> Login(string email, string password) =>
        client.PostAsJsonAsync("/login", new { email, password });

    private sealed record LoginResponse(string AccessToken);
}
```

#### Authorization Tests

Configure the fixture clients with distinct identities and seed resource `42` for the owner.

```csharp
using System.Net;
using System.Net.Http;
using System.Threading.Tasks;
using Xunit;

public abstract class AuthorizationTests(HttpClient owner, HttpClient otherUser, HttpClient admin)
{
    [Fact]
    public async Task GetResource_OwnerAccess_ReturnsOk()
    {
        using var response = await owner.GetAsync("/resources/42");
        Assert.Equal(HttpStatusCode.OK, response.StatusCode);
    }

    [Fact]
    public async Task GetResource_OtherUserAccess_ReturnsForbidden()
    {
        using var response = await otherUser.GetAsync("/resources/42");
        Assert.Equal(HttpStatusCode.Forbidden, response.StatusCode);
    }

    [Fact]
    public async Task AdminEndpoint_NonAdmin_ReturnsForbidden()
    {
        using var response = await owner.GetAsync("/admin");
        Assert.Equal(HttpStatusCode.Forbidden, response.StatusCode);
    }

    [Fact]
    public async Task AdminEndpoint_Admin_ReturnsOk()
    {
        using var response = await admin.GetAsync("/admin");
        Assert.Equal(HttpStatusCode.OK, response.StatusCode);
    }
}
```

#### Input Validation Tests

```csharp
using System.Net;
using System.Net.Http;
using System.Net.Http.Json;
using System.Threading.Tasks;
using Xunit;

public abstract class InputValidationTests(HttpClient client)
{
    [Theory]
    [InlineData("<script>alert('xss')</script>")]
    [InlineData("'; DROP TABLE users; --")]
    [InlineData("../../../etc/passwd")]
    public async Task Endpoint_InvalidResourceName_RejectsInput(string input)
    {
        using var response = await client.PostAsJsonAsync("/resources", new { name = input });
        Assert.Equal(HttpStatusCode.BadRequest, response.StatusCode);
    }
}
```

### Security Testing Checklist

```markdown
- [ ] All auth paths have positive/negative tests
- [ ] Authorization tested for each role
- [ ] Input validation has boundary tests
- [ ] Error responses tested for information leak
- [ ] Crypto functions have correctness tests
- [ ] Rate limiting tested
- [ ] Session handling tested
```

---