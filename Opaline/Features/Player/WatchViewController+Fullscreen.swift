import UIKit

/// Where the player has to go back to once fullscreen ends.
struct FullscreenSnapshot {
    let superview: UIView
    let frame: CGRect
    let host: UIView
}

// MARK: - Fullscreen

extension WatchViewController {
    func enterFullscreen(playerView: VideoPlayerView, animated: Bool = true) {
        guard let window = view.window else {
            return
        }
        let host = fullscreenHost(in: window)
        detachPlayerToHost(playerView, host: host)
        updateQueueBar()
        setNeedsStatusBarAppearanceUpdate()
        setNeedsUpdateOfHomeIndicatorAutoHidden()
        guard animated else {
            playerView.frame = host.bounds
            playerView.applyAutoZoomIfNeeded()
            return
        }
        UIView.animate(
            withDuration: 0.25,
            delay: 0,
            options: .curveEaseInOut,
            animations: {
                playerView.frame = host.bounds
            },
            completion: { _ in
                playerView.applyAutoZoomIfNeeded()
            }
        )
    }

    private func fullscreenHost(in window: UIWindow) -> UIView {
        #if LEGACY_IOS9
        // A direct UIWindow child is drawn on iOS 9 but can miss button taps,
        // particularly on iPad. The root controller's view has UIKit's normal
        // hit-testing and still fills the window when the status bar is hidden.
        return window.rootViewController?.view ?? window
        #else
        return window
        #endif
    }

    private func detachPlayerToHost(
        _ playerView: VideoPlayerView,
        host: UIView
    ) {
        let frameInHost = playerView.convert(
            playerView.bounds, to: host
        )
        fullscreenSnapshot = FullscreenSnapshot(
            superview: playerView.superview ?? view,
            frame: playerView.frame,
            host: host
        )
        playerView.removeFromSuperview()
        playerView.translatesAutoresizingMaskIntoConstraints = true
        // Allow the player to resize with the window when the device rotates while
        // in fullscreen, so the video fills the screen in the new orientation.
        playerView.autoresizingMask = [.flexibleWidth, .flexibleHeight]
        playerView.frame = frameInHost
        host.addSubview(playerView)
        playerView.isFullscreen = true
    }

    func exitFullscreen(playerView: VideoPlayerView, animated: Bool = true) {
        guard let snap = fullscreenSnapshot else {
            return
        }
        // Ask for the status bar now, so it slides back in alongside the
        // shrinking player. Asked for at the end of the animation instead, it
        // arrives half a second late and shoves the settled layout down.
        isLeavingFullscreen = true
        setNeedsStatusBarAppearanceUpdate()
        let target = snap.superview.convert(snap.frame, to: snap.host)
        guard animated else {
            restoreFromFullscreen(playerView: playerView, snapshot: snap)
            return
        }
        UIView.animate(
            withDuration: 0.25,
            delay: 0,
            options: .curveEaseInOut,
            animations: {
                playerView.frame = target
            }, completion: { [weak self] _ in
                self?.restoreFromFullscreen(
                    playerView: playerView, snapshot: snap
                )
            }
        )
    }

    func restoreFromFullscreen(
        playerView: VideoPlayerView,
        snapshot: FullscreenSnapshot
    ) {
        playerView.removeFromSuperview()
        let sv = snapshot.superview
        playerView.transform = .identity
        playerView.bounds = CGRect(origin: .zero, size: snapshot.frame.size)
        playerView.translatesAutoresizingMaskIntoConstraints = false
        playerView.autoresizingMask = []
        sv.addSubview(playerView)
        NSLayoutConstraint.activate([
            playerView.leadingAnchor.constraint(equalTo: sv.leadingAnchor),
            playerView.trailingAnchor.constraint(equalTo: sv.trailingAnchor),
            playerView.topAnchor.constraint(equalTo: sv.topAnchor),
            playerView.bottomAnchor.constraint(equalTo: sv.bottomAnchor)
        ])
        playerView.isFullscreen = false
        fullscreenSnapshot = nil
        isLeavingFullscreen = false
        setNeedsStatusBarAppearanceUpdate()
        setNeedsUpdateOfHomeIndicatorAutoHidden()
        updateLayoutForSize()
        updateQueueBar()
    }
}
