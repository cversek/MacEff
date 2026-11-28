### Added

- **MIS-0012 (Draft): the attention stack and interrupt model** (`framework/mis/MIS-0012-the-attention-stack-and-interrupt-model.md`). A first draft for open discussion. Each operator message opens a frame, classified by its origin, with the handle a reply needs. A remote message is acknowledged on its own channel first. A frame closes only on a recorded return, and the frame below is named as owed next. Open frames survive a compaction, show on the hook line while open, and are measured per subclass from the event log. 24 requirements, nine open questions, no code yet.
