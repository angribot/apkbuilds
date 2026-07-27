# Keep published build identities immutable

Once a build identity is published, its contents never change. Any change to a
package origin must advance its package version or package revision; this
prevents one identity from naming different content and lets publication skip
known builds.
