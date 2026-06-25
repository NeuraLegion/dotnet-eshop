namespace eShop.Ordering.API.Infrastructure.Services;

public class IdentityService(IHttpContextAccessor context) : IIdentityService
{
    public string GetUserIdentity()
        => context.HttpContext?.User.FindFirst("sub")?.Value ?? "dast-user";

    public string GetUserName()
        => context.HttpContext?.User.Identity?.Name ?? "dast-user";
}
