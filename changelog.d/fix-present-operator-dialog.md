### Fixed

- **A dialog the operator is present to answer is no longer denied because a sprint or play time is running** (`permission_watch.full_autonomy_denial`, autonomous_operation 5.5, #963): with `permissions.deny_under_full_autonomy` on, the PermissionRequest hook denied every dialog in AUTO_MODE while a sprint or play time was in active scope, including the questions and approvals of an operator sitting at the keyboard. It now denies only when the operator is away: USER_REMOTE, or USER_IDLE once the idle timeout has passed without a message from them.
