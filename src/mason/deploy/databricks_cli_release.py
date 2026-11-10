"""The Databricks CLI this Mason release runs. Written by `just release::pin-cli`; don't edit."""

VERSION = "1.23.0"

# The SHA-256 of each platform's zip archive, from the release's published checksums.
CHECKSUMS = {
    "darwin_amd64": "cc368545f77bfed08512d1494a8ef001efc50bddd4a111b834f11540dc429d50",
    "darwin_arm64": "1d632228c749deecb5812e9ca35490b02382d47d5c05dc6e466dff747fd5248a",
    "linux_amd64": "1b95b717b3fa97d8f53c85953d6b94aea3ab9a0c035b38ca492875b13b5f5b3d",
    "linux_arm64": "5f29cab04f98d7f5da0fcf69ca7a912d22ec737fdb113633c0d91600d8d172c2",
    "windows_amd64": "40e8bed527a8fa093ea30a2dbe9321bba95cc53078f097e6269a575233383d36",
    "windows_arm64": "92fbd95eb4c2960a66f5eb221db6a0438bd440a11f39231289bdcaf490a39cbe",
}
