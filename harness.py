import os
import json
import logging
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional

from flask import Flask, request, Response

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ordering-harness")

PORT = int(os.getenv("PORT", "3001"))
APP_ROOT = Path("/app")
PROJECT = APP_ROOT / "src" / "Ordering.API"
HARNESS_PROJ_DIR = APP_ROOT / ".harness_ordering"
HARNESS_PROJ = HARNESS_PROJ_DIR / "Harness.csproj"
HARNESS_SRC = HARNESS_PROJ_DIR / "Program.cs"

loaded_targets: Dict[str, Dict[str, Any]] = {}


def plain(text: str, status: int = 200) -> Response:
    return Response(text, status=status, content_type="text/plain; charset=utf-8")


def run_cmd(cmd: List[str], cwd: Optional[Path] = None, timeout: int = 180) -> subprocess.CompletedProcess:
    return subprocess.run(
        cmd,
        cwd=str(cwd) if cwd else None,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=timeout,
    )


def detect_target_framework() -> str:
    csproj = PROJECT / "Ordering.API.csproj"
    content = csproj.read_text(encoding="utf-8")
    for tfm in ["net10.0", "net9.0", "net8.0", "net7.0", "net6.0"]:
        if tfm in content:
            return tfm
    return "net10.0"


def build_harness_project() -> None:
    HARNESS_PROJ_DIR.mkdir(parents=True, exist_ok=True)
    tfm = detect_target_framework()

    csproj = f"""<Project Sdk="Microsoft.NET.Sdk">
  <PropertyGroup>
    <OutputType>Exe</OutputType>
    <TargetFramework>{tfm}</TargetFramework>
    <ImplicitUsings>enable</ImplicitUsings>
    <Nullable>enable</Nullable>
    <LangVersion>latest</LangVersion>
    <EnableDefaultCompileItems>true</EnableDefaultCompileItems>
  </PropertyGroup>

  <ItemGroup>
    <ProjectReference Include="../src/Ordering.API/Ordering.API.csproj" />
    <ProjectReference Include="../src/Ordering.Infrastructure/Ordering.Infrastructure.csproj" />
    <ProjectReference Include="../src/Ordering.Domain/Ordering.Domain.csproj" />
    <ProjectReference Include="../src/EventBus/EventBus.csproj" />
    <ProjectReference Include="../src/IntegrationEventLogEF/IntegrationEventLogEF.csproj" />
  </ItemGroup>
</Project>
"""
    HARNESS_PROJ.write_text(csproj, encoding="utf-8")

    program = r'''
using System.Text.Json;
using System.Linq;
using MediatR;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.Logging;
using Microsoft.Extensions.Logging.Abstractions;
using eShop.EventBus.Abstractions;
using eShop.EventBus.Events;
using eShop.IntegrationEventLogEF.Services;
using eShop.Ordering.API.Application.Commands;
using eShop.Ordering.API.Application.IntegrationEvents;
using eShop.Ordering.API.Application.IntegrationEvents.Events;
using eShop.Ordering.API.Application.Models;
using eShop.Ordering.API.Application.Queries;
using eShop.Ordering.API.Extensions;
using eShop.Ordering.API.Infrastructure.Services;
using eShop.Ordering.Infrastructure;
using eShop.Ordering.Infrastructure.Idempotency;
using eShop.Ordering.Infrastructure.Repositories;

public class HarnessInput
{
    public JsonElement? message { get; set; }
    public JsonElement? item { get; set; }
    public JsonElement? basketItems { get; set; }
    public JsonElement? command { get; set; }
    public JsonElement? evt { get; set; }
    public JsonElement? id { get; set; }
    public JsonElement? userId { get; set; }
    public JsonElement? userName { get; set; }
    public JsonElement? city { get; set; }
    public JsonElement? street { get; set; }
    public JsonElement? state { get; set; }
    public JsonElement? country { get; set; }
    public JsonElement? zipcode { get; set; }
    public JsonElement? zipCode { get; set; }
    public JsonElement? cardNumber { get; set; }
    public JsonElement? cardHolderName { get; set; }
    public JsonElement? cardExpiration { get; set; }
    public JsonElement? cardSecurityNumber { get; set; }
    public JsonElement? cardTypeId { get; set; }
}

public class StubIdentityService : IIdentityService
{
    public string GetUserIdentity() => "harness-user";
    public string GetUserName() => "harness";
}

public class StubMediator : IMediator
{
    public Func<object, CancellationToken, Task<object?>>? Sender { get; set; }

    public Task Publish(object notification, CancellationToken cancellationToken = default) => Task.CompletedTask;
    public Task Publish<TNotification>(TNotification notification, CancellationToken cancellationToken = default) where TNotification : INotification => Task.CompletedTask;

    public async Task<TResponse> Send<TResponse>(IRequest<TResponse> request, CancellationToken cancellationToken = default)
    {
        if (Sender != null)
        {
            var result = await Sender(request!, cancellationToken);
            if (result is TResponse cast) return cast;
            if (result == null) return default!;
        }
        return default!;
    }

    public Task<object?> Send(object request, CancellationToken cancellationToken = default)
        => Sender != null ? Sender(request, cancellationToken) : Task.FromResult<object?>(null);

    public IAsyncEnumerable<TResponse> CreateStream<TResponse>(IStreamRequest<TResponse> request, CancellationToken cancellationToken = default)
        => AsyncEnumerable.Empty<TResponse>();

    public IAsyncEnumerable<object?> CreateStream(object request, CancellationToken cancellationToken = default)
        => AsyncEnumerable.Empty<object?>();
}

public class StubEventBus : IEventBus
{
    public Task PublishAsync(IntegrationEvent @event) => Task.CompletedTask;
    public void Subscribe<T, TH>() where T : IntegrationEvent where TH : IIntegrationEventHandler<T> { }
    public void Unsubscribe<T, TH>() where TH : IIntegrationEventHandler<T> where T : IntegrationEvent { }
}

public class DuplicateTrueIdentifiedHandler<T> : IdentifiedCommandHandler<T, bool> where T : IRequest<bool>
{
    public DuplicateTrueIdentifiedHandler(IMediator mediator, IRequestManager requestManager)
        : base(mediator, requestManager, NullLogger<IdentifiedCommandHandler<T, bool>>.Instance) { }

    protected override bool CreateResultForDuplicateRequest() => true;
}

public static class Harness
{
    static readonly JsonSerializerOptions JsonOpts = new() { PropertyNameCaseInsensitive = true };

    static string ConnString =>
        Environment.GetEnvironmentVariable("ConnectionStrings__orderingdb")
        ?? Environment.GetEnvironmentVariable("ConnectionStrings__OrderingDB")
        ?? Environment.GetEnvironmentVariable("ConnectionStrings__ordering")
        ?? "Host=orderingdb;Database=OrderingDB;Username=postgres;Password=yourWeak(!)Password";

    static OrderingContext CreateContext(IMediator? mediator = null)
    {
        var builder = new DbContextOptionsBuilder<OrderingContext>();
        builder.UseNpgsql(ConnString);
        return mediator == null ? new OrderingContext(builder.Options) : new OrderingContext(builder.Options, mediator);
    }

    static T Deserialize<T>(JsonElement? el)
    {
        if (el == null) throw new Exception("Missing JSON payload");
        return JsonSerializer.Deserialize<T>(el.Value.GetRawText(), JsonOpts)!;
    }

    static string Serialize(object? obj) => JsonSerializer.Serialize(obj, JsonOpts);

    static DateTime ParseDateTime(JsonElement? el)
    {
        if (el == null || !el.HasValue)
            throw new Exception("Missing cardExpiration");

        var v = el.Value;
        if (v.ValueKind == JsonValueKind.String)
            return DateTime.Parse(v.GetString()!);

        return v.Deserialize<DateTime>(JsonOpts);
    }

    static int ParseRequiredInt(JsonElement? el, string name)
    {
        if (el == null || !el.HasValue)
            throw new Exception("Missing " + name);

        var v = el.Value;
        return v.ValueKind == JsonValueKind.String ? int.Parse(v.GetString()!) : v.GetInt32();
    }

    static bool IsDbTarget(string target) =>
        target is "OrderQueries.GetOrderAsync"
            or "OrderQueries.GetOrdersFromUserAsync"
            or "CancelOrderCommandHandler.Handle"
            or "ShipOrderCommandHandler.Handle"
            or "CreateOrderCommandHandler.Handle"
            or "IdentifiedCommandHandler<T,R>.Handle"
            or "OrderingIntegrationEventService.AddAndSaveEventAsync";

    static object DbUnavailable(string target, Exception ex) =>
        new
        {
            target,
            dbAvailable = false,
            error = ex.GetType().Name,
            message = ex.Message
        };

    public static async Task<int> Main(string[] args)
    {
        try
        {
            var target = args[0];
            var json = args.Length > 1 ? args[1] : "{}";
            var input = JsonSerializer.Deserialize<HarnessInput>(json, JsonOpts) ?? new HarnessInput();
            var result = await Invoke(target, input);
            Console.Write(Serialize(result));
            return 0;
        }
        catch (Exception ex)
        {
            Console.Error.WriteLine(ex.ToString());
            return 1;
        }
    }

    static async Task<object?> Invoke(string target, HarnessInput input)
    {
        switch (target)
        {
            case "CreateOrderDraftCommandHandler.Handle":
            {
                var msg = Deserialize<CreateOrderDraftCommand>(input.message);
                var handler = new CreateOrderDraftCommandHandler();
                return await handler.Handle(msg, CancellationToken.None);
            }

            case "BasketItemExtensions.ToOrderItemDTO":
            {
                var item = Deserialize<BasketItem>(input.item);
                return item.ToOrderItemDTO();
            }

            case "BasketItemExtensions.ToOrderItemsDTO":
            {
                var items = Deserialize<List<BasketItem>>(input.basketItems);
                return items.ToOrderItemsDTO().ToList();
            }

            case "CreateOrderCommand.CreateOrderCommand":
            {
                var basketItems = Deserialize<List<BasketItem>>(input.basketItems);
                var userId = input.userId?.GetString() ?? "";
                var userName = input.userName?.GetString() ?? "";
                var city = input.city?.GetString() ?? "";
                var street = input.street?.GetString() ?? "";
                var state = input.state?.GetString() ?? "";
                var country = input.country?.GetString() ?? "";
                var zipcode = (input.zipcode ?? input.zipCode)?.GetString() ?? "";
                var cardNumber = input.cardNumber?.GetString() ?? "";
                var cardHolderName = input.cardHolderName?.GetString() ?? "";
                var cardExpiration = ParseDateTime(input.cardExpiration);
                var cardSecurityNumber = input.cardSecurityNumber?.GetString() ?? "";
                var cardTypeId = input.cardTypeId == null || !input.cardTypeId.HasValue
                    ? 0
                    : (input.cardTypeId.Value.ValueKind == JsonValueKind.String
                        ? int.Parse(input.cardTypeId.Value.GetString()!)
                        : input.cardTypeId.Value.GetInt32());

                var cmd = new CreateOrderCommand(
                    basketItems, userId, userName, city, street, state, country, zipcode,
                    cardNumber, cardHolderName, cardExpiration, cardSecurityNumber, cardTypeId);
                return cmd;
            }

            case "OrderQueries.GetOrderAsync":
            {
                try
                {
                    var id = ParseRequiredInt(input.id, "id");
                    using var ctx = CreateContext();
                    var q = new OrderQueries(ctx);
                    return await q.GetOrderAsync(id);
                }
                catch (Exception ex) when (IsDbTarget(target))
                {
                    return DbUnavailable(target, ex);
                }
            }

            case "OrderQueries.GetOrdersFromUserAsync":
            {
                try
                {
                    var userId = input.userId?.GetString() ?? throw new Exception("Missing userId");
                    using var ctx = CreateContext();
                    var q = new OrderQueries(ctx);
                    return await q.GetOrdersFromUserAsync(userId);
                }
                catch (Exception ex) when (IsDbTarget(target))
                {
                    return DbUnavailable(target, ex);
                }
            }

            case "CancelOrderCommandHandler.Handle":
            {
                try
                {
                    var cmd = Deserialize<CancelOrderCommand>(input.command);
                    var mediator = new StubMediator();
                    using var ctx = CreateContext(mediator);
                    var repo = new OrderRepository(ctx);
                    var handler = new CancelOrderCommandHandler(repo);
                    return await handler.Handle(cmd, CancellationToken.None);
                }
                catch (Exception ex) when (IsDbTarget(target))
                {
                    return DbUnavailable(target, ex);
                }
            }

            case "ShipOrderCommandHandler.Handle":
            {
                try
                {
                    var cmd = Deserialize<ShipOrderCommand>(input.command);
                    var mediator = new StubMediator();
                    using var ctx = CreateContext(mediator);
                    var repo = new OrderRepository(ctx);
                    var handler = new ShipOrderCommandHandler(repo);
                    return await handler.Handle(cmd, CancellationToken.None);
                }
                catch (Exception ex) when (IsDbTarget(target))
                {
                    return DbUnavailable(target, ex);
                }
            }

            case "CreateOrderCommandHandler.Handle":
            {
                try
                {
                    var msg = Deserialize<CreateOrderCommand>(input.message);
                    var mediator = new StubMediator();
                    using var ctx = CreateContext(mediator);

                    if (!ctx.HasActiveTransaction)
                    {
                        await ctx.BeginTransactionAsync();
                    }

                    var repo = new OrderRepository(ctx);
                    var logService = new IntegrationEventLogService<OrderingContext>(ctx);
                    var orderingSvc = new OrderingIntegrationEventService(
                        new StubEventBus(),
                        ctx,
                        logService,
                        NullLogger<OrderingIntegrationEventService>.Instance
                    );
                    var handler = new CreateOrderCommandHandler(
                        mediator,
                        orderingSvc,
                        repo,
                        new StubIdentityService(),
                        NullLogger<CreateOrderCommandHandler>.Instance
                    );
                    return await handler.Handle(msg, CancellationToken.None);
                }
                catch (Exception ex) when (IsDbTarget(target))
                {
                    return DbUnavailable(target, ex);
                }
            }

            case "IdentifiedCommandHandler<T,R>.Handle":
            {
                try
                {
                    var root = input.message ?? throw new Exception("Missing message");
                    var msg = root.Value;

                    var reqId = msg.GetProperty("id").Deserialize<Guid>(JsonOpts);
                    var cmdEl = msg.GetProperty("command");

                    IRequest<bool> inner;
                    if (cmdEl.TryGetProperty("orderNumber", out _))
                    {
                        if (cmdEl.TryGetProperty("ship", out var shipEl) &&
                            (shipEl.ValueKind == JsonValueKind.True || shipEl.ValueKind == JsonValueKind.False) &&
                            shipEl.GetBoolean())
                        {
                            inner = cmdEl.Deserialize<ShipOrderCommand>(JsonOpts)!;
                        }
                        else
                        {
                            inner = cmdEl.Deserialize<CancelOrderCommand>(JsonOpts)!;
                        }
                    }
                    else if (cmdEl.TryGetProperty("userId", out _))
                    {
                        inner = cmdEl.Deserialize<CreateOrderCommand>(JsonOpts)!;
                    }
                    else
                    {
                        throw new Exception("Unsupported wrapped command shape");
                    }

                    var mediator = new StubMediator();
                    using var ctx = CreateContext(mediator);

                    if (inner is CreateOrderCommand && !ctx.HasActiveTransaction)
                    {
                        await ctx.BeginTransactionAsync();
                    }

                    var reqMgr = new RequestManager(ctx);

                    mediator.Sender = async (req, ct) =>
                    {
                        if (req is CancelOrderCommand c)
                        {
                            var repo = new OrderRepository(ctx);
                            var h = new CancelOrderCommandHandler(repo);
                            return await h.Handle(c, ct);
                        }

                        if (req is ShipOrderCommand s)
                        {
                            var repo = new OrderRepository(ctx);
                            var h = new ShipOrderCommandHandler(repo);
                            return await h.Handle(s, ct);
                        }

                        if (req is CreateOrderCommand co)
                        {
                            var repo = new OrderRepository(ctx);
                            var logService = new IntegrationEventLogService<OrderingContext>(ctx);
                            var orderingSvc = new OrderingIntegrationEventService(
                                new StubEventBus(),
                                ctx,
                                logService,
                                NullLogger<OrderingIntegrationEventService>.Instance);
                            var h = new CreateOrderCommandHandler(
                                mediator,
                                orderingSvc,
                                repo,
                                new StubIdentityService(),
                                NullLogger<CreateOrderCommandHandler>.Instance);
                            return await h.Handle(co, ct);
                        }

                        return false;
                    };

                    if (inner is CancelOrderCommand cancel)
                    {
                        var identified = new IdentifiedCommand<CancelOrderCommand, bool>(cancel, reqId);
                        var h = new DuplicateTrueIdentifiedHandler<CancelOrderCommand>(mediator, reqMgr);
                        return await h.Handle(identified, CancellationToken.None);
                    }

                    if (inner is ShipOrderCommand ship)
                    {
                        var identified = new IdentifiedCommand<ShipOrderCommand, bool>(ship, reqId);
                        var h = new DuplicateTrueIdentifiedHandler<ShipOrderCommand>(mediator, reqMgr);
                        return await h.Handle(identified, CancellationToken.None);
                    }

                    if (inner is CreateOrderCommand create)
                    {
                        var identified = new IdentifiedCommand<CreateOrderCommand, bool>(create, reqId);
                        var h = new DuplicateTrueIdentifiedHandler<CreateOrderCommand>(mediator, reqMgr);
                        return await h.Handle(identified, CancellationToken.None);
                    }

                    throw new Exception("Unsupported identified command type");
                }
                catch (Exception ex) when (IsDbTarget(target))
                {
                    return DbUnavailable(target, ex);
                }
            }

            case "OrderingIntegrationEventService.AddAndSaveEventAsync":
            {
                try
                {
                    IntegrationEvent evt;
                    if (input.evt == null)
                        throw new Exception("Missing evt");

                    var evtEl = input.evt.Value;
                    var userId = evtEl.TryGetProperty("userId", out var userIdEl) && userIdEl.ValueKind == JsonValueKind.String
                        ? userIdEl.GetString()!
                        : "harness-user";

                    if (evtEl.TryGetProperty("id", out var idEl) && idEl.ValueKind != JsonValueKind.Null)
                    {
                        evt = new OrderStartedIntegrationEvent(userId)
                        {
                            Id = idEl.ValueKind == JsonValueKind.String
                                ? Guid.Parse(idEl.GetString()!)
                                : idEl.Deserialize<Guid>(JsonOpts)
                        };
                    }
                    else
                    {
                        evt = new OrderStartedIntegrationEvent(userId);
                    }

                    var mediator = new StubMediator();
                    using var ctx = CreateContext(mediator);
                    var tx = await ctx.BeginTransactionAsync();
                    if (tx == null) throw new Exception("Failed to begin transaction");

                    try
                    {
                        var logService = new IntegrationEventLogService<OrderingContext>(ctx);
                        var svc = new OrderingIntegrationEventService(
                            new StubEventBus(),
                            ctx,
                            logService,
                            NullLogger<OrderingIntegrationEventService>.Instance
                        );
                        await svc.AddAndSaveEventAsync(evt);
                        await tx.CommitAsync();
                        return new { saved = true, evt.Id };
                    }
                    catch
                    {
                        await tx.RollbackAsync();
                        throw;
                    }
                }
                catch (Exception ex) when (IsDbTarget(target))
                {
                    return DbUnavailable(target, ex);
                }
            }

            default:
                throw new Exception("Unknown target: " + target);
        }
    }
}
'''
    HARNESS_SRC.write_text(program, encoding="utf-8")

    restore = run_cmd(["dotnet", "restore", str(HARNESS_PROJ)], cwd=APP_ROOT, timeout=300)
    if restore.returncode != 0:
        raise RuntimeError(f"dotnet restore failed:\n{restore.stdout}\n{restore.stderr}")

    build = run_cmd(["dotnet", "build", str(HARNESS_PROJ), "-c", "Release"], cwd=APP_ROOT, timeout=300)
    if build.returncode != 0:
        raise RuntimeError(f"dotnet build failed:\n{build.stdout}\n{build.stderr}")


def probe_target(name: str, sample: Dict[str, Any]) -> bool:
    proc = run_cmd(
        ["dotnet", "run", "--project", str(HARNESS_PROJ), "-c", "Release", "--no-build", "--", name, json.dumps(sample)],
        cwd=APP_ROOT,
        timeout=30,
    )
    if proc.returncode != 0:
        logger.warning("Skipping target %s: %s", name, proc.stderr.strip() or proc.stdout.strip())
        return False
    return True


def invoke_target(name: str, payload: Dict[str, Any]) -> str:
    proc = run_cmd(
        ["dotnet", "run", "--project", str(HARNESS_PROJ), "-c", "Release", "--no-build", "--", name, json.dumps(payload)],
        cwd=APP_ROOT,
        timeout=45,
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or proc.stdout.strip() or f"Invocation failed for {name}")
    return proc.stdout


TARGETS = [
    {
        "name": "CreateOrderDraftCommandHandler.Handle",
        "route": "/harness/createorderdraftcommandhandler-handle",
        "method": "POST",
        "sample": {
            "message": {
                "buyerId": "user-123",
                "items": [
                    {
                        "id": "1",
                        "productId": 10,
                        "productName": "test",
                        "unitPrice": 12.5,
                        "oldUnitPrice": 13,
                        "quantity": 2,
                        "pictureUrl": "http://example/1.png",
                    }
                ],
            }
        },
    },
    {
        "name": "BasketItemExtensions.ToOrderItemDTO",
        "route": "/harness/basketitemextensions-toorderitemdto",
        "method": "POST",
        "sample": {
            "item": {
                "id": "1",
                "productId": 10,
                "productName": "test",
                "unitPrice": 12.5,
                "oldUnitPrice": 13,
                "quantity": 2,
                "pictureUrl": "http://example/1.png",
            }
        },
    },
    {
        "name": "BasketItemExtensions.ToOrderItemsDTO",
        "route": "/harness/basketitemextensions-toorderitemsdto",
        "method": "POST",
        "sample": {
            "basketItems": [
                {
                    "id": "1",
                    "productId": 10,
                    "productName": "test",
                    "unitPrice": 12.5,
                    "oldUnitPrice": 13,
                    "quantity": 2,
                    "pictureUrl": "http://example/1.png",
                }
            ]
        },
    },
    {
        "name": "CreateOrderCommand.CreateOrderCommand",
        "route": "/harness/createordercommand-createordercommand",
        "method": "POST",
        "sample": {
            "basketItems": [
                {
                    "id": "1",
                    "productId": 10,
                    "productName": "test",
                    "unitPrice": 12.5,
                    "oldUnitPrice": 13,
                    "quantity": 2,
                    "pictureUrl": "http://example/1.png",
                }
            ],
            "userId": "user-123",
            "userName": "alice",
            "city": "NYC",
            "street": "1 Main St",
            "state": "NY",
            "country": "US",
            "zipcode": "10001",
            "cardNumber": "XXXXXXXXXXXX1111",
            "cardHolderName": "Alice",
            "cardExpiration": "2030-01-01T00:00:00Z",
            "cardSecurityNumber": "123",
            "cardTypeId": 1,
        },
    },
    {
        "name": "OrderQueries.GetOrderAsync",
        "route": "/harness/orderqueries-getorderasync",
        "method": "GET",
        "sample": {"id": 1},
    },
    {
        "name": "OrderQueries.GetOrdersFromUserAsync",
        "route": "/harness/orderqueries-getordersfromuserasync",
        "method": "GET",
        "sample": {"userId": "user-123"},
    },
    {
        "name": "CancelOrderCommandHandler.Handle",
        "route": "/harness/cancelordercommandhandler-handle",
        "method": "PUT",
        "sample": {"command": {"orderNumber": 1}},
    },
    {
        "name": "ShipOrderCommandHandler.Handle",
        "route": "/harness/shipordercommandhandler-handle",
        "method": "PUT",
        "sample": {"command": {"orderNumber": 1}},
    },
    {
        "name": "CreateOrderCommandHandler.Handle",
        "route": "/harness/createordercommandhandler-handle",
        "method": "POST",
        "sample": {
            "message": {
                "userId": "user-123",
                "userName": "alice",
                "city": "NYC",
                "street": "1 Main St",
                "state": "NY",
                "country": "US",
                "zipCode": "10001",
                "cardNumber": "XXXXXXXXXXXX1111",
                "cardHolderName": "Alice",
                "cardExpiration": "2030-01-01T00:00:00Z",
                "cardSecurityNumber": "123",
                "cardTypeId": 1,
                "orderItems": [
                    {
                        "productId": 10,
                        "productName": "test",
                        "unitPrice": 12.5,
                        "discount": 0,
                        "units": 2,
                        "pictureUrl": "http://example/1.png",
                    }
                ],
            }
        },
    },
    {
        "name": "IdentifiedCommandHandler<T,R>.Handle",
        "route": "/harness/identifiedcommandhandler-t--r--handle",
        "method": "PUT",
        "sample": {
            "message": {
                "id": "11111111-1111-1111-1111-111111111111",
                "command": {"orderNumber": 1},
            }
        },
    },
    {
        "name": "OrderingIntegrationEventService.AddAndSaveEventAsync",
        "route": "/harness/orderingintegrationeventservice-addandsaveeventasync",
        "method": "POST",
        "sample": {
            "evt": {
                "id": "11111111-1111-1111-1111-111111111111",
                "userId": "user-123"
            }
        },
    },
]


@app.get("/health")
def health() -> Response:
    return plain("ok", 200)


def get_payload() -> Dict[str, Any]:
    if request.method == "GET":
        if request.is_json:
            data = request.get_json(silent=True)
            if isinstance(data, dict):
                return data
        return {k: v for k, v in request.args.items()}
    data = request.get_json(silent=True)
    return data if isinstance(data, dict) else {}


def register_route(route: str, method: str, target_name: str):
    def handler():
        try:
            payload = get_payload()
            output = invoke_target(target_name, payload)
            return plain(output, 200)
        except subprocess.TimeoutExpired:
            return plain(f"Invocation timed out for {target_name}", 504)
        except Exception as e:
            return plain(str(e), 500)

    endpoint_name = f"{method}_{route}".replace("/", "_").replace("-", "_").replace(".", "_")
    if endpoint_name not in app.view_functions:
        app.add_url_rule(route, endpoint=endpoint_name, view_func=handler, methods=[method])


def bootstrap():
    try:
        build_harness_project()
    except Exception as e:
        logger.warning("Harness backend build failed: %s", e)

    for target in TARGETS:
        try:
            loaded_targets[target["name"]] = target
            register_route(target["route"], target["method"], target["name"])
            logger.info("Loaded target %s on %s", target["name"], target["route"])
        except Exception as e:
            logger.warning("Failed loading target %s: %s", target["name"], e)

    try:
        for target in TARGETS:
            try:
                probe_ok = probe_target(target["name"], target["sample"])
                if not probe_ok:
                    logger.warning("Probe failed for target %s; route remains registered", target["name"])
            except Exception as e:
                logger.warning("Probe error for target %s: %s", target["name"], e)
    except Exception as e:
        logger.warning("Probe phase failed: %s", e)


bootstrap()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=PORT)
