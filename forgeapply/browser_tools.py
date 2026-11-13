"""Typed, bounded browser requests; no arbitrary JavaScript or model-supplied selectors."""
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator


class BrowserTarget(BaseModel):
    model_config = ConfigDict(extra='forbid')
    role: Literal['button','link','textbox','combobox','option','checkbox','radio'] | None = None
    name: str = Field(default='', max_length=230)
    label: str | None = Field(default=None, max_length=230)
    field_index: int | None = Field(default=None, ge=0, le=99)
    frame_index: int = Field(default=0, ge=0, le=20)

    @model_validator(mode='after')
    def one_locator(self):
        if sum((self.role is not None, self.label is not None, self.field_index is not None)) != 1:
            raise ValueError('Choose exactly one role, label or inspected field index')
        if self.role and not self.name:
            raise ValueError('An exact accessible name is required')
        return self


class BrowserToolCall(BaseModel):
    model_config = ConfigDict(extra='forbid')
    action: Literal['inspect','accessibility','navigate','click','fill','select','check',
                    'scroll','screenshot','upload','wait','double_click','type_text','clear',
                    'press_key','hover','switch_tab','extract_text','validation','wait_navigation']
    target: BrowserTarget | None = None
    value: str = Field(default='', max_length=5000)
    url: str = Field(default='', max_length=2000)
    language: Literal['en','it'] = 'en'
    direction: Literal['up','down'] = 'down'
    distance: int = Field(default=600, ge=1, le=2000)
    timeout_ms: int = Field(default=6000, ge=100, le=15000)
    snapshot_id: str | None = None
    tab_index: int = Field(default=0, ge=0, le=20)

    @model_validator(mode='after')
    def require_target(self):
        if self.action in {'click','fill','select','check','wait','double_click','type_text','clear','press_key','hover'} and self.target is None:
            raise ValueError('This action requires an inspected target')
        if self.action == 'navigate' and not self.url:
            raise ValueError('Navigation requires a URL')
        return self
