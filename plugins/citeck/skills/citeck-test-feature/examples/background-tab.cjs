// Use only with the dedicated Chrome instance owned by the test run.
async function createBackgroundPage(browser, { timeout = 5000 } = {}) {
  const cdp = await browser.newBrowserCDPSession();
  let targetId;
  try {
    ({ targetId } = await cdp.send('Target.createTarget', {
      url: 'about:blank',
      background: true,
    }));
    const deadline = Date.now() + timeout;
    do {
      for (const context of browser.contexts()) {
        for (const page of context.pages()) {
          if (page.isClosed()) continue;
          const session = await context.newCDPSession(page);
          try {
            const { targetInfo } = await session.send('Target.getTargetInfo');
            if (targetInfo.targetId === targetId) return { page, targetId };
          } finally {
            await session.detach();
          }
        }
      }
      await new Promise(resolve => setTimeout(resolve, 50));
    } while (Date.now() < deadline);
    throw new Error('The background tab did not become available to Playwright');
  } catch (error) {
    if (targetId) {
      await cdp.send('Target.closeTarget', { targetId }).catch(() => {});
    }
    throw error;
  } finally {
    await cdp.detach();
  }
}

module.exports = { createBackgroundPage };
