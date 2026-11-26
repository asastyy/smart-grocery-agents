"""Inventory rules: suggestions are not stock and planning never consumes food."""
from collections.abc import Sequence
from datetime import date
from decimal import Decimal
from typing import Literal
from uuid import uuid4

from smart_grocery.schemas.foodcom import Ingredient, Unit
from smart_grocery.schemas.integration import InventoryItem
from smart_grocery.schemas.personalization import (
    ConsumptionPlan,
    InventoryAllocation,
    InventoryEvent,
    InventoryShortage,
    InventorySuggestion,
    InventoryUpdate,
)


def available_inventory(
    inventory: Sequence[InventoryItem], *, as_of: date | None = None
) -> list[InventoryItem]:
    today = as_of or date.today()
    return [
        item for item in inventory
        if item.status == "available"
        and item.confidence == 1
        and item.quantity > 0
        and (item.expiry_date is None or item.expiry_date >= today)
    ]


def suggest_inventory_from_purchase(
    ingredient_id: str,
    display_name: str,
    *,
    quantity: Decimal | None = None,
    unit: Unit | None = None,
    source: Literal["purchase_history", "receipt", "barcode", "photo"] = "purchase_history",
    confidence: Decimal = Decimal("0.7"),
) -> InventorySuggestion:
    return InventorySuggestion(
        suggestion_id=f"suggestion-{uuid4().hex}",
        ingredient_id=ingredient_id,
        display_name=display_name,
        quantity=quantity,
        unit=unit,
        source=source,
        confidence=confidence,
    )


def confirm_inventory_suggestion(
    suggestion: InventorySuggestion,
    *,
    quantity: Decimal | None = None,
    unit: Unit | None = None,
) -> InventoryItem:
    confirmed_quantity = quantity if quantity is not None else suggestion.quantity
    confirmed_unit = unit if unit is not None else suggestion.unit
    if confirmed_quantity is None or confirmed_unit is None:
        raise ValueError("quantity and unit must be confirmed before adding inventory")
    return InventoryItem(
        inventory_item_id=f"inventory-{uuid4().hex}",
        ingredient_id=suggestion.ingredient_id,
        display_name=suggestion.display_name,
        quantity=confirmed_quantity,
        unit=confirmed_unit,
        expiry_date=suggestion.expiry_date,
        source=suggestion.source,
        confidence=Decimal("1"),
    )


def plan_consumption(
    inventory: Sequence[InventoryItem],
    requirements: Sequence[Ingredient],
    *,
    as_of: date | None = None,
) -> ConsumptionPlan:
    """Allocate confirmed stock FEFO; incompatible units are never converted."""
    usable = available_inventory(inventory, as_of=as_of)
    explicit_ids = [item.inventory_item_id for item in usable if item.inventory_item_id is not None]
    if len(explicit_ids) != len(set(explicit_ids)):
        raise ValueError("inventory_item_id must be unique")
    remaining = {id(item): item.quantity for item in usable}
    allocations: list[InventoryAllocation] = []
    shortages: list[InventoryShortage] = []
    for requirement in requirements:
        needed = requirement.quantity
        candidates = [
            item for item in usable
            if item.ingredient_id == requirement.ingredient_id and item.unit == requirement.unit
        ]
        candidates.sort(key=lambda item: (
            item.expiry_date or date.max,
            item.opened is not True,
            item.inventory_item_id or "",
        ))
        for item in candidates:
            if needed <= 0:
                break
            used = min(needed, remaining[id(item)])
            if used <= 0:
                continue
            item_id = item.inventory_item_id or f"legacy-{id(item)}"
            allocations.append(InventoryAllocation(
                inventory_item_id=item_id,
                ingredient_id=item.ingredient_id,
                quantity=used,
                unit=item.unit,
            ))
            remaining[id(item)] -= used
            needed -= used
        if needed > 0:
            shortages.append(InventoryShortage(
                ingredient_id=requirement.ingredient_id,
                quantity=needed,
                unit=requirement.unit,
            ))
    return ConsumptionPlan(allocations=allocations, shortages=shortages)


def apply_consumption(
    inventory: Sequence[InventoryItem],
    plan: ConsumptionPlan,
    *,
    confirmed: bool,
) -> InventoryUpdate:
    """Consume only after explicit cooking confirmation; return copies, not mutations."""
    if not confirmed:
        raise ValueError("inventory consumption requires explicit confirmation")
    by_id = {
        (item.inventory_item_id or f"legacy-{id(item)}"): item.model_copy(deep=True)
        for item in inventory
    }
    events: list[InventoryEvent] = []
    for allocation in plan.allocations:
        item = by_id.get(allocation.inventory_item_id)
        if item is None or item.ingredient_id != allocation.ingredient_id or item.unit != allocation.unit:
            raise ValueError(f"inventory item {allocation.inventory_item_id} changed after planning")
        if allocation.quantity > item.quantity:
            raise ValueError(f"inventory item {allocation.inventory_item_id} has insufficient quantity")
        item.quantity -= allocation.quantity
        action = "deplete" if item.quantity == 0 else "consume"
        if item.quantity == 0:
            item.status = "depleted"
        events.append(InventoryEvent(
            inventory_item_id=allocation.inventory_item_id,
            ingredient_id=allocation.ingredient_id,
            action=action,
            quantity=allocation.quantity,
            unit=allocation.unit,
        ))
    return InventoryUpdate(inventory=list(by_id.values()), events=events)
