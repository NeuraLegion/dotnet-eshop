using System.Reflection;
using System.Text;
using System.Text.Json;
using System.Text.Json.Serialization;
using eShop.EventBus.Abstractions;
using eShop.EventBus.Events;
using eShop.IntegrationEventLogEF.Services;
using eShop.Ordering.API.Application.Commands;
using eShop.Ordering.API.Application.IntegrationEvents;
using eShop.Ordering.API.Application.Models;
using eShop.Ordering.API.Application.Queries;
using eShop.Ordering.API.Infrastructure.Services;
using eShop.Ordering.Domain.AggregatesModel.BuyerAggregate;
using eShop.Ordering.Domain.AggregatesModel.OrderAggregate;
using eShop.Ordering.Domain.Seedwork;
using eShop.Ordering.Infrastructure;
using eShop.Ordering.Infrastructure.Repositories;
using MediatR;
using Microsoft.AspNetCore.Builder;
using Microsoft.AspNetCore.Http;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.Logging;
using CardTypeQueryModel = eShop.Ordering.API.Application.Queries.CardType;
using QueryOrder = eShop.Ordering.API.Application.Queries.Order;

var builder = WebApplication.CreateBuilder(args);

builder.WebHost.UseUrls($"http://0.0.0.0:{Environment.GetEnvironmentVariable("PORT") ?? "3001"}");

builder.Services.AddRouting();
builder.Services.AddLogging();
builder.Services.ConfigureHttpJsonOptions(options =>
{
    options.SerializerOptions.PropertyNameCaseInsensitive = true;
    options.SerializerOptions.DefaultIgnoreCondition = JsonIgnoreCondition.Never;
});

var connectionString =
    Environment.GetEnvironmentVariable("ConnectionStrings__OrderingDB") ??
    "Host=orderingdb;Database=OrderingDB;Username=postgres;Password=yourWeak(!)Password";

builder.Services.AddDbContext<OrderingContext>(options =>
{
    options.UseNpgsql(connectionString);
});

var app = builder.Build();

app.MapGet("/health", () => Results.Text("ok", "text/plain"));

static IResult Plain(object? value, int statusCode = 200)
{
    string text;
    if (value is null)
    {
        text = "null";
    }
    else if (value is string s)
    {
        text = s;
    }
    else
    {
        text = JsonSerializer.Serialize(value);
    }

    return Results.Text(text, "text/plain", Encoding.UTF8, statusCode);
}

static async Task<T?> ReadJsonBodyAsync<T>(HttpRequest request)
{
    return await JsonSerializer.DeserializeAsync<T>(
        request.Body,
        new JsonSerializerOptions
        {
            PropertyNameCaseInsensitive = true
        });
}

static string ExceptionText(Exception ex)
{
    var baseEx = ex.GetBaseException();
    return $"{baseEx.GetType().FullName}: {baseEx.Message}";
}

static T SetProperty<T>(T instance, string propertyName, object? value)
{
    var prop = typeof(T).GetProperty(propertyName, BindingFlags.Public | BindingFlags.Instance);
    prop?.SetValue(instance, value);
    return instance;
}

static CreateOrderCommand BuildCreateOrderCommandFromSample(CreateOrderCommandRequest dto)
{
    var command = new CreateOrderCommand();

    SetProperty(command, nameof(CreateOrderCommand.UserId), dto.UserId);
    SetProperty(command, nameof(CreateOrderCommand.UserName), dto.UserName);
    SetProperty(command, nameof(CreateOrderCommand.City), dto.City);
    SetProperty(command, nameof(CreateOrderCommand.Street), dto.Street);
    SetProperty(command, nameof(CreateOrderCommand.State), dto.State);
    SetProperty(command, nameof(CreateOrderCommand.Country), dto.Country);
    SetProperty(command, nameof(CreateOrderCommand.ZipCode), dto.ZipCode);
    SetProperty(command, nameof(CreateOrderCommand.CardNumber), dto.CardNumber);
    SetProperty(command, nameof(CreateOrderCommand.CardHolderName), dto.CardHolderName);
    SetProperty(command, nameof(CreateOrderCommand.CardExpiration), dto.CardExpiration);
    SetProperty(command, nameof(CreateOrderCommand.CardSecurityNumber), dto.CardSecurityNumber);
    SetProperty(command, nameof(CreateOrderCommand.CardTypeId), dto.CardTypeId);

    var field = typeof(CreateOrderCommand).GetField("_orderItems", BindingFlags.NonPublic | BindingFlags.Instance);
    field?.SetValue(command, dto.OrderItems ?? new List<OrderItemDTO>());

    return command;
}

static async Task SeedIfNeededAsync(OrderingContext db)
{
    await db.Database.EnsureCreatedAsync();

    if (!await db.CardTypes.AnyAsync())
    {
        db.CardTypes.AddRange(
            new CardType { Id = 1, Name = "Visa" },
            new CardType { Id = 2, Name = "MasterCard" },
            new CardType { Id = 3, Name = "Amex" }
        );
    }

    if (!await db.Buyers.AnyAsync(b => b.IdentityGuid == "dast-user"))
    {
        db.Buyers.Add(new Buyer("dast-user", "DAST User"));
    }

    if (!await db.Orders.AnyAsync(o => o.Id == 123))
    {
        var address = new Address("1 Main St", "Testville", "CA", "US", "12345");
        var order = new eShop.Ordering.Domain.AggregatesModel.OrderAggregate.Order(
            "dast-user",
            "alice",
            address,
            1,
            "XXXXXXXXXXXX1111",
            "123",
            "Alice",
            DateTime.UtcNow.AddYears(2)
        );
        order.AddOrderItem(10, "Widget", 12.5m, 0m, "https://example.test/img.png", 2);
        db.Orders.Add(order);
    }

    await db.SaveChangesAsync();
}

var loaded = new Dictionary<string, bool>();

void SafeMap(string key, Action mapper)
{
    try
    {
        mapper();
        loaded[key] = true;
        app.Logger.LogInformation("Loaded harness route for {Key}", key);
    }
    catch (Exception ex)
    {
        loaded[key] = false;
        app.Logger.LogWarning(ex, "Failed to load harness route for {Key}", key);
    }
}

SafeMap("CreateOrderDraftCommandHandler.Handle", () =>
{
    app.MapPost("/harness/createorderdraftcommandhandler-handle", async (HttpRequest request) =>
    {
        try
        {
            var payload = await ReadJsonBodyAsync<CreateOrderDraftHandleRequest>(request) ?? new CreateOrderDraftHandleRequest();
            var handler = new CreateOrderDraftCommandHandler();
            var result = await handler.Handle(
                payload.Message ?? new CreateOrderDraftCommand("user-123", new List<BasketItem>()),
                CancellationToken.None);
            return Plain(result);
        }
        catch (Exception ex)
        {
            return Plain(ExceptionText(ex), 500);
        }
    });
});

SafeMap("BasketItemExtensions.ToOrderItemDTO", () =>
{
    app.MapPost("/harness/basketitemextensions-toorderitemdto", async (HttpRequest request) =>
    {
        try
        {
            var item = await ReadJsonBodyAsync<BasketItem>(request) ?? new BasketItem();
            var result = eShop.Ordering.API.Extensions.BasketItemExtensions.ToOrderItemDTO(item);
            return Plain(result);
        }
        catch (Exception ex)
        {
            return Plain(ExceptionText(ex), 500);
        }
    });
});

SafeMap("BasketItemExtensions.ToOrderItemsDTO", () =>
{
    app.MapPost("/harness/basketitemextensions-toorderitemsdto", async (HttpRequest request) =>
    {
        try
        {
            var items = await ReadJsonBodyAsync<List<BasketItem>>(request) ?? new List<BasketItem>();
            var result = eShop.Ordering.API.Extensions.BasketItemExtensions.ToOrderItemsDTO(items).ToList();
            return Plain(result);
        }
        catch (Exception ex)
        {
            return Plain(ExceptionText(ex), 500);
        }
    });
});

SafeMap("OrderQueries.Handle", () =>
{
    app.MapGet("/harness/orderqueries-handle", async (HttpRequest request, OrderingContext db) =>
    {
        try
        {
            await SeedIfNeededAsync(db);
            var idText = request.Query["id"].FirstOrDefault() ?? "123";
            var id = int.Parse(idText);
            var queries = new OrderQueries(db);
            QueryOrder result = await queries.GetOrderAsync(id);
            return Plain(result);
        }
        catch (Exception ex)
        {
            return Plain(ExceptionText(ex), 500);
        }
    });
});

SafeMap("OrderQueries.GetOrdersFromUserAsync", () =>
{
    app.MapGet("/harness/orderqueries-getordersfromuserasync", async (HttpRequest request, OrderingContext db) =>
    {
        try
        {
            await SeedIfNeededAsync(db);
            var userId = request.Query["userId"].FirstOrDefault() ?? "dast-user";
            var queries = new OrderQueries(db);
            var result = await queries.GetOrdersFromUserAsync(userId);
            return Plain(result);
        }
        catch (Exception ex)
        {
            return Plain(ExceptionText(ex), 500);
        }
    });
});

SafeMap("OrderQueries.GetCardTypesAsync", () =>
{
    app.MapGet("/harness/orderqueries-getcardtypesasync", async (OrderingContext db) =>
    {
        try
        {
            await SeedIfNeededAsync(db);
            var queries = new OrderQueries(db);
            IEnumerable<CardTypeQueryModel> result = await queries.GetCardTypesAsync();
            return Plain(result);
        }
        catch (Exception ex)
        {
            return Plain(ExceptionText(ex), 500);
        }
    });
});

SafeMap("CreateOrderCommandHandler.Handle", () =>
{
    app.MapPost("/harness/createordercommandhandler-handle", async (HttpRequest request, OrderingContext db, ILoggerFactory loggerFactory) =>
    {
        try
        {
            await SeedIfNeededAsync(db);

            var payload = await ReadJsonBodyAsync<CreateOrderCommandHandleRequest>(request) ?? new CreateOrderCommandHandleRequest();
            var repository = new OrderRepository(db);
            var mediator = new NoopMediator();
            var identityService = new StubIdentityService();
            var eventService = new StubOrderingIntegrationEventService();
            var logger = loggerFactory.CreateLogger<CreateOrderCommandHandler>();

            var handler = new CreateOrderCommandHandler(mediator, eventService, repository, identityService, logger);
            var command = BuildCreateOrderCommandFromSample(payload.Message ?? new CreateOrderCommandRequest());
            var result = await handler.Handle(command, CancellationToken.None);
            return Plain(new
            {
                Result = result,
                SavedEvents = eventService.SavedEvents.Select(e => new { e.Id, Type = e.GetType().FullName }).ToList()
            });
        }
        catch (Exception ex)
        {
            return Plain(ExceptionText(ex), 500);
        }
    });
});

SafeMap("OrderingIntegrationEventService.AddAndSaveEventAsync", () =>
{
    app.MapPost("/harness/orderingintegrationeventservice-addandsaveeventasync", async (HttpRequest request, OrderingContext db, ILoggerFactory loggerFactory) =>
    {
        try
        {
            await db.Database.EnsureCreatedAsync();

            var evt = await ReadJsonBodyAsync<IntegrationEvent>(request) ?? new IntegrationEvent();
            var logger = loggerFactory.CreateLogger<OrderingIntegrationEventService>();
            var eventBus = new StubEventBus();
            var eventLogService = new StubIntegrationEventLogService();
            var service = new OrderingIntegrationEventService(eventBus, db, eventLogService, logger);

            using var tx = await db.Database.BeginTransactionAsync();
            typeof(OrderingContext)
                .GetField("_currentTransaction", BindingFlags.NonPublic | BindingFlags.Instance)
                ?.SetValue(db, tx);

            await service.AddAndSaveEventAsync(evt);

            return Plain(new
            {
                EventId = evt.Id,
                SavedCount = eventLogService.Saved.Count
            });
        }
        catch (Exception ex)
        {
            return Plain(ExceptionText(ex), 500);
        }
    });
});

SafeMap("CancelOrderCommandHandler.Handle", () =>
{
    app.MapPut("/harness/cancelordercommandhandler-handle", async (HttpRequest request, OrderingContext db) =>
    {
        try
        {
            await SeedIfNeededAsync(db);

            var payload = await ReadJsonBodyAsync<CancelOrderHandleRequest>(request) ?? new CancelOrderHandleRequest();
            var repository = new OrderRepository(db);
            var handler = new CancelOrderCommandHandler(repository);
            var result = await handler.Handle(payload.Command ?? new CancelOrderCommand(123), CancellationToken.None);
            return Plain(result);
        }
        catch (Exception ex)
        {
            return Plain(ExceptionText(ex), 500);
        }
    });
});

SafeMap("ShipOrderCommandHandler.Handle", () =>
{
    app.MapPut("/harness/shipordercommandhandler-handle", async (HttpRequest request, OrderingContext db) =>
    {
        try
        {
            await SeedIfNeededAsync(db);

            var payload = await ReadJsonBodyAsync<ShipOrderHandleRequest>(request) ?? new ShipOrderHandleRequest();
            var order123 = await db.Orders.FindAsync((payload.Command?.OrderNumber) ?? 123);
            if (order123 != null)
            {
                try
                {
                    order123.SetAwaitingValidationStatus();
                    order123.SetStockConfirmedStatus();
                    order123.SetPaidStatus();
                    await db.SaveChangesAsync();
                }
                catch
                {
                }
            }

            var repository = new OrderRepository(db);
            var handler = new ShipOrderCommandHandler(repository);
            var result = await handler.Handle(payload.Command ?? new ShipOrderCommand(123), CancellationToken.None);
            return Plain(result);
        }
        catch (Exception ex)
        {
            return Plain(ExceptionText(ex), 500);
        }
    });
});

app.Run();

public sealed class CreateOrderDraftHandleRequest
{
    public CreateOrderDraftCommand? Message { get; set; }
    public string? CancellationToken { get; set; }
}

public sealed class CreateOrderCommandHandleRequest
{
    public CreateOrderCommandRequest? Message { get; set; }
    public string? CancellationToken { get; set; }
}

public sealed class CancelOrderHandleRequest
{
    public CancelOrderCommand? Command { get; set; }
    public string? CancellationToken { get; set; }
}

public sealed class ShipOrderHandleRequest
{
    public ShipOrderCommand? Command { get; set; }
    public string? CancellationToken { get; set; }
}

public sealed class CreateOrderCommandRequest
{
    public string UserId { get; set; } = "user-123";
    public string UserName { get; set; } = "alice";
    public string City { get; set; } = "Testville";
    public string Street { get; set; } = "1 Main St";
    public string State { get; set; } = "CA";
    public string Country { get; set; } = "US";
    public string ZipCode { get; set; } = "12345";
    public string CardNumber { get; set; } = "XXXXXXXXXXXX1111";
    public string CardHolderName { get; set; } = "Alice";
    public DateTime CardExpiration { get; set; } = DateTime.Parse("2030-01-01T00:00:00Z").ToUniversalTime();
    public string CardSecurityNumber { get; set; } = "123";
    public int CardTypeId { get; set; } = 1;
    public List<OrderItemDTO> OrderItems { get; set; } = new()
    {
        new OrderItemDTO
        {
            ProductId = 10,
            ProductName = "Widget",
            UnitPrice = 12.5m,
            Discount = 0m,
            Units = 2,
            PictureUrl = "https://example.test/img.png"
        }
    };
}

public sealed class StubIdentityService : IIdentityService
{
    public string GetUserIdentity() => "dast-user";
    public string GetUserName() => "DAST User";
}

public sealed class StubOrderingIntegrationEventService : IOrderingIntegrationEventService
{
    public List<IntegrationEvent> SavedEvents { get; } = new();

    public Task AddAndSaveEventAsync(IntegrationEvent evt)
    {
        SavedEvents.Add(evt);
        return Task.CompletedTask;
    }

    public Task PublishEventsThroughEventBusAsync(Guid transactionId) => Task.CompletedTask;
}

public sealed class StubIntegrationEventLogService : IIntegrationEventLogService
{
    public List<(IntegrationEvent Event, object? Transaction)> Saved { get; } = new();

    public Task<IEnumerable<eShop.IntegrationEventLogEF.IntegrationEventLogEntry>> RetrieveEventLogsPendingToPublishAsync(Guid transactionId)
        => Task.FromResult<IEnumerable<eShop.IntegrationEventLogEF.IntegrationEventLogEntry>>(Array.Empty<eShop.IntegrationEventLogEF.IntegrationEventLogEntry>());

    public Task SaveEventAsync(IntegrationEvent @event, Microsoft.EntityFrameworkCore.Storage.IDbContextTransaction transaction)
    {
        Saved.Add((@event, transaction));
        return Task.CompletedTask;
    }

    public Task MarkEventAsPublishedAsync(Guid eventId) => Task.CompletedTask;
    public Task MarkEventAsInProgressAsync(Guid eventId) => Task.CompletedTask;
    public Task MarkEventAsFailedAsync(Guid eventId) => Task.CompletedTask;
}

public sealed class StubEventBus : IEventBus
{
    public Task PublishAsync(IntegrationEvent @event) => Task.CompletedTask;
}

public sealed class NoopMediator : IMediator
{
    public Task Publish(object notification, CancellationToken cancellationToken = default) => Task.CompletedTask;
    public Task Publish<TNotification>(TNotification notification, CancellationToken cancellationToken = default)
        where TNotification : INotification => Task.CompletedTask;
    public Task<TResponse> Send<TResponse>(IRequest<TResponse> request, CancellationToken cancellationToken = default)
        => Task.FromResult(default(TResponse)!);
    public Task Send<TRequest>(TRequest request, CancellationToken cancellationToken = default)
        where TRequest : IRequest => Task.CompletedTask;
    public IAsyncEnumerable<object?> CreateStream(object request, CancellationToken cancellationToken = default)
        => AsyncEnumerable.Empty<object?>();
    public IAsyncEnumerable<TResponse> CreateStream<TResponse>(IStreamRequest<TResponse> request, CancellationToken cancellationToken = default)
        => AsyncEnumerable.Empty<TResponse>();
}
