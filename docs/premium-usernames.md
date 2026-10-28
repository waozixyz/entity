# Premium usernames

The Alias page asks the account's selected Daochi node for availability and
an exact integer Dew price. New usernames use 4–32 lowercase ASCII letters,
numbers or underscores. Existing usernames, including older shorter names,
remain owned and free to keep.

Available premium names show their price and open a confirmation modal.
Checking availability, opening the modal, cancelling, and topping up never
purchase a name. Insufficient funds offer the host's existing Dew top-up flow;
the person returns to confirm the purchase afterward.

Native providers persist the account, node, alias, price and random request ID
before sending a purchase. An uncertain result retains that intent across a
restart. An explicit retry reuses the same request ID, including when the
remaining balance is below the original price. The node's idempotent purchase
endpoint prevents a second debit. Changing accounts or nodes never reuses a
different account's intent. Hosts implementing management must durably handle
`alias_purchase_load`, `alias_purchase_save` and `alias_purchase_clear` before
enabling purchases; a missing callback fails closed.

Local validation:

- `make premium-alias-test` covers input normalization, bounded strict quotes,
  exact integer prices, grandfathered names, intent round-trips and payment
  actions.
- `make premium-alias-node-test` uses throwaway accounts and a private Daochi
  node for quotes, unchanged legacy saves, insufficient funds, purchases,
  taken/owned names and restart retry after a successful debit but failed
  local save. It checks that the signed ledger is unchanged by the retry.
