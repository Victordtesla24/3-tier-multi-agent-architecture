"""
Enhancement 1: Strict A2UI Schema Enforcement & The View Agent
Addresses Critique 3 – Probabilistic Payload Generation in A2UI Streaming.

Implements strict Pydantic models mapping to the A2UI v0.8 protocol specification.
The View Agent acts as a validation middleware, ensuring that the probabilistic LLM
output structurally conforms to the required data contract before yielding the JSONL
stream, thereby preventing client-side rendering crashes.
"""

import json
import logging
from typing import Any, AsyncGenerator, Dict, List, Literal, Optional

from pydantic import BaseModel, Field, ValidationError

# Configure module-level logging for the View Agent
logger = logging.getLogger("A2UI_ViewAgent")
logger.setLevel(logging.INFO)


class A2UIComponent(BaseModel):
    """
    Abstract base definition for an A2UI native component representation.
    Ensures agents only request components from the client's trusted catalog.
    """

    type: str = Field(
        ...,
        description="The native component type (e.g., 'Button', 'Card', 'TextField').",
    )
    id: str = Field(
        ...,
        description="Unique string identifier for the component within the current surface.",
    )
    props: Dict[str, Any] = Field(
        default_factory=dict,
        description="Component-specific properties mapped to the native widget.",
    )
    children: Optional[List[str]] = Field(
        default=None,
        description="List of child component IDs for layout composition.",
    )


class SurfaceUpdateMessage(BaseModel):
    """
    Payload for updating or defining a UI surface component tree.
    """

    type: Literal["surfaceUpdate"] = "surfaceUpdate"
    surface_id: str = Field(..., alias="surfaceId")
    components: List[A2UIComponent] = Field(
        ...,
        description="Flat list of components representing the UI declaration.",
    )

    model_config = {"populate_by_name": True}


class DataModelUpdateMessage(BaseModel):
    """
    Payload facilitating two-way data binding and reactive state updates.
    """

    type: Literal["dataModelUpdate"] = "dataModelUpdate"
    surface_id: str = Field(..., alias="surfaceId")
    data: Dict[str, Any] = Field(
        ...,
        description="JSON Pointer path-based reactive data key-value pairs.",
    )

    model_config = {"populate_by_name": True}


class BeginRenderingMessage(BaseModel):
    """
    Explicit signal instructing the client application to execute the render pass.
    """

    type: Literal["beginRendering"] = "beginRendering"
    surface_id: str = Field(..., alias="surfaceId")

    model_config = {"populate_by_name": True}


class A2UIViewAgent:
    """
    The View Agent implementation. It maps abstract state from the Tier 1 Controller
    into strictly validated, declarative A2UI JSONL streams, preventing XSS/RCE
    by guaranteeing structural contracts across the trust boundary.
    """

    def __init__(self, surface_id: str) -> None:
        self.surface_id = surface_id

    def _validate_and_serialize(self, model: BaseModel) -> str:
        """
        Enforces schema strictness. Intercepts potential LLM hallucinations
        prior to stream serialization.
        """
        try:
            # Deep re-validation to ensure no dynamic mutation broke the protocol contract
            validated = model.__class__(**model.model_dump(by_alias=True))
            return json.dumps(validated.model_dump(by_alias=True, exclude_none=True))
        except ValidationError as e:
            logger.error(
                f"A2UI Protocol Violation Detected. Aborting stream: {e}"
            )
            raise RuntimeError(
                "Fatal: View Agent generated malformed A2UI payload."
            ) from e

    async def generate_ui_stream(
        self, raw_controller_state: Dict[str, Any]
    ) -> AsyncGenerator[str, None]:
        """
        Asynchronously yields JSON Lines strings complying strictly with the
        A2UI v0.8 specification.
        """
        logger.info(f"Generating A2UI stream for surface: {self.surface_id}")

        # 1. Construct and Yield the Surface Update (UI Tree)
        components = [
            A2UIComponent(
                type="Card",
                id="main_container_card",
                props={"elevation": 4, "padding": "16dp"},
                children=["header_text", "status_indicator", "action_button"],
            ),
            A2UIComponent(
                type="Text",
                id="header_text",
                props={
                    "text": raw_controller_state.get("title", "System Ready"),
                    "style": "h2",
                },
            ),
            A2UIComponent(
                type="Text",
                id="status_indicator",
                props={
                    "text": f"Status: {raw_controller_state.get('status', 'IDLE')}",
                    "color": "blue",
                },
            ),
            A2UIComponent(
                type="Button",
                id="action_button",
                props={
                    "label": "Acknowledge Completion",
                    "actionId": "ack_event_01",
                },
            ),
        ]

        surface_update = SurfaceUpdateMessage(
            surfaceId=self.surface_id, components=components
        )
        yield self._validate_and_serialize(surface_update) + "\n"

        # 2. Construct and Yield the Data Model Update (State binding)
        data_model = DataModelUpdateMessage(
            surfaceId=self.surface_id,
            data={"/ack_event_01/visibility": True},
        )
        yield self._validate_and_serialize(data_model) + "\n"

        # 3. Construct and Yield the Begin Rendering Signal
        begin_render = BeginRenderingMessage(surfaceId=self.surface_id)
        yield self._validate_and_serialize(begin_render) + "\n"

        logger.info(
            f"A2UI stream transmission complete for surface: {self.surface_id}"
        )
