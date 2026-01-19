from typing import Any, Dict, List
from textual import on
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical, Container, VerticalScroll
from textual.widgets import Tree, Static, Input, Button, Label, Switch, Select, TextArea
from textual.message import Message
from textual.widgets.tree import TreeNode

class SettingsView(Vertical):
    """A view for browsing and editing nested settings."""

    class SettingsChanged(Message):
        """Posted when settings are saved."""
        def __init__(self, new_settings: dict) -> None:
            self.new_settings = new_settings
            super().__init__()

    def __init__(self, initial_settings: dict = None, **kwargs) -> None:
        super().__init__(**kwargs)
        self.settings_data = initial_settings or {}
        self.schema_data = {} 
        self.current_node_path: List[str] = []
        self.input_widgets: Dict[str, Any] = {}
        self.initial_form_values: Dict[str, Any] = {}

    def compose(self) -> ComposeResult:
        with Horizontal(id="settings-container"):
            with Vertical(id="settings-sidebar"):
                yield Label("Configuration", id="settings-sidebar-title")
                yield Tree("Root", id="settings-tree")
            
            with Vertical(id="settings-content"):
                yield Label("Select a category to edit", id="settings-content-title")
                with VerticalScroll(id="settings-form-container"):
                    pass 
                
                with Horizontal(id="settings-actions"):
                    yield Button("Save Changes", id="btn-save-settings", variant="success", disabled=True)
                    yield Button("Refresh", id="btn-refresh-settings", variant="primary")

    async def on_mount(self) -> None:
        # Load data if not already present
        if not self.settings_data or not self.schema_data:
            await self.on_refresh_settings()

    async def load_schema(self) -> None:
        if not hasattr(self.app, "api"):
            return
        resp, err = await self.app.api.get_schema(self.app.settings.get("riven_key"))
        if not err and resp:
            # Store the entire schema response
            self.schema_data = resp
            self.app.log_message("Settings schema loaded successfully.")

    def _get_schema_entry(self, key_path: List[str]) -> dict:
        """Finds schema metadata for a nested key path, resolving $ref pointers."""
        current = self.schema_data
        
        for part in key_path:
            if not isinstance(current, dict):
                return {}
            
            # Resolve $ref if current node is a pointer
            if "$ref" in current:
                ref_path = current["$ref"].split("/")
                # Handle common #/$defs/ or #/definitions/
                defs = self.schema_data.get("$defs", self.schema_data.get("definitions", {}))
                if len(ref_path) > 2 and ref_path[1] in ["$defs", "definitions"]:
                    current = defs.get(ref_path[2], {})
                else:
                    return {}

            properties = current.get("properties", {})
            if part in properties:
                current = properties[part]
            elif "additionalProperties" in current and isinstance(current["additionalProperties"], dict):
                current = current["additionalProperties"]
            else:
                return {}

        # Final check: if the leaf node itself is a $ref, resolve it one last time
        if isinstance(current, dict) and "$ref" in current:
            ref_path = current["$ref"].split("/")
            defs = self.schema_data.get("$defs", self.schema_data.get("definitions", {}))
            if len(ref_path) > 2 and ref_path[1] in ["$defs", "definitions"]:
                current = defs.get(ref_path[2], {})

        return current

    def build_tree(self, data: dict) -> None:
        tree = self.query_one("#settings-tree", Tree)
        tree.clear()
        tree.root.label = "Settings"
        tree.root.expand()
        
        # 1. Root scalars -> General
        root_scalars = {k: v for k, v in data.items() if not isinstance(v, dict)}
        if root_scalars:
            tree.root.add("General", data=root_scalars)
        
        # 2. Nested objects -> Sub-nodes
        for key, value in data.items():
            if isinstance(value, dict):
                node = tree.root.add(key, data=value, expand=False)
                node.json_key = key
                self._add_nodes(node, value, [key])

    def _add_nodes(self, parent_node: TreeNode, data: dict, path: List[str]) -> None:
        for key, value in data.items():
            if isinstance(value, dict):
                current_path = path + [key]
                node = parent_node.add(key, data=value, expand=False)
                node.json_key = key
                self._add_nodes(node, value, current_path)

    @on(Tree.NodeSelected)
    def on_tree_node_selected(self, event: Tree.NodeSelected) -> None:
        node = event.node
        self.current_node_path = self._get_node_path_keys(node)
        
        if node.label.plain == "General":
            self.show_form("General Settings", node.data, [])
        elif isinstance(node.data, dict):
            self.show_form(node.label.plain, node.data, self.current_node_path)

    def _get_node_path_keys(self, node: TreeNode) -> List[str]:
        if node.label.plain == "General": return []
        path = []
        curr = node
        while curr.parent:
            if hasattr(curr, "json_key"):
                path.insert(0, curr.json_key)
            curr = curr.parent
        return path

    def show_form(self, title: str, data: dict, path: List[str]) -> None:
        self.query_one("#settings-content-title", Label).update(f"Editing: {title}")
        container = self.query_one("#settings-form-container")
        container.remove_children()
        
        self.input_widgets = {}
        self.initial_form_values = {}
        has_fields = False
        
        for key in sorted(data.keys()):
            value = data[key]
            if not isinstance(value, dict):
                has_fields = True
                self.initial_form_values[key] = value
                schema_entry = self._get_schema_entry(path + [key])
                self._create_field(container, key, value, schema_entry)
        
        if not has_fields:
            container.mount(Label("No editable fields in this category.", classes="no-fields-label"))
            self.query_one("#btn-save-settings").disabled = True
        else:
            self.query_one("#btn-save-settings").disabled = False

    def _create_field(self, container: Container, key: str, value: Any, schema: dict) -> None:
        display_name = schema.get("title", key.replace("_", " ").title())
        description_text = schema.get("description", "")
        widget_id = f"setting-{key}"
        
        label = Label(display_name, classes="setting-label")
        
        # 1. Determine Widget Type & Add Instructions for Lists
        is_list = False
        if schema.get("enum"):
            options = [(str(x), str(x)) for x in schema["enum"]]
            widget = Select(options, value=str(value), id=widget_id)
        elif isinstance(value, bool):
            widget = Switch(value=value, id=widget_id)
        elif isinstance(value, list):
            is_list = True
            str_val = "\n".join(map(str, value)) if value else ""
            widget = TextArea(str_val, id=widget_id)
            widget.styles.height = 5
            widget.meta_type = "list"
        else:
            val_str = str(value) if value is not None else ""
            widget = Input(value=val_str, id=widget_id)
            widget.meta_type = "int" if isinstance(value, int) else "float" if isinstance(value, float) else "str"

        self.input_widgets[key] = widget
        
        # 2. Form Layout
        row = Horizontal(label, widget, classes="setting-row")
        children = [row]
        
        # 3. Handle Description and List Instructions
        instruction = "(One value per line) " if is_list else ""
        if description_text or instruction:
            full_desc = f"   [italic]{instruction}{description_text}[/]"
            children.append(Label(full_desc, classes="setting-description"))
            
        field_v = Vertical(*children, classes="setting-field-v")
        container.mount(field_v)

    def _parse_widget_value(self, key: str, widget: Any) -> Any:
        """Helper to get and cast the value from a widget based on its type."""
        if isinstance(widget, Switch):
            return widget.value
        elif isinstance(widget, Select):
            return widget.value
        elif isinstance(widget, TextArea):
            return [x.strip() for x in widget.text.split("\n") if x.strip()]
        elif isinstance(widget, Input):
            val = widget.value
            mtype = getattr(widget, "meta_type", "str")
            if mtype == "int":
                return int(val) if val.isdigit() or (val.startswith("-") and val[1:].isdigit()) else 0
            elif mtype == "float":
                try: return float(val)
                except: return 0.0
            else:
                return val
        return None

    @on(Button.Pressed, "#btn-save-settings")
    async def on_save_settings(self) -> None:
        # 1. Detect Changes
        changes = {}
        for key, widget in self.input_widgets.items():
            new_val = self._parse_widget_value(key, widget)
            old_val = self.initial_form_values.get(key)
            
            # Simple equality check for strings, bools, ints, and lists
            if new_val != old_val:
                changes[key] = new_val
        
        if not changes:
            self.app.notify("No changes detected.")
            return

        # 2. Build the nested payload (the delta)
        payload = {}
        target_payload = payload
        
        if self.current_node_path:
            for path_part in self.current_node_path[:-1]:
                target_payload[path_part] = {}
                target_payload = target_payload[path_part]
            target_payload[self.current_node_path[-1]] = changes
        else:
            payload = changes # Root/General level

        # 3. Update the local master copy
        target_master = self.settings_data
        for path_part in self.current_node_path:
            if path_part not in target_master:
                target_master[path_part] = {}
            target_master = target_master[path_part]
        target_master.update(changes)

        # 4. Call API with ONLY the payload (delta)
        self.app.notify("Saving changes...")
        self.app.log_message(f"Settings View: Saving delta: {payload}")
        resp, err = await self.app.api.update_settings(payload, self.app.settings.get("riven_key"))
        
        if err:
            self.app.notify(f"Error: {err}", severity="error")
            self.app.log_message(f"Settings View: Save Error: {err}")
        else:
            self.app.notify("Settings updated successfully!", severity="success")
            self.app.log_message("Settings View: Save Successful")
            # Update initial values so a second click doesn't send the same delta
            self.initial_form_values.update(changes)
            self.post_message(self.SettingsChanged(self.settings_data))

    @on(Button.Pressed, "#btn-refresh-settings")
    async def on_refresh_settings(self) -> None:
        self.notify("Loading...")
        if not hasattr(self.app, "api"): return

        await self.load_schema()
        resp, err = await self.app.api.get_settings(self.app.settings.get("riven_key"))
        
        if resp:
            self.settings_data = resp
            self.build_tree(self.settings_data)
            self.query_one("#settings-form-container").remove_children()
            self.notify("Updated.")