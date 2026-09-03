## User

The configuration file format MUST NOT change. Python owns configuration semantics.

## Assistant

We decided to keep materialized locations internal and use Calendar.resolve().

## User

Do not use field projection because it would create a speculative public interface.
The current behavior ignores inherited periods. The desired behavior is to merge them.
