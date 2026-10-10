(function (global) {
  'use strict';
  function initDisconnect(data, psl) {
    const domains = data.domains || {};
    const companies = data.companies || {};
    const domainKeys = new Set(Object.keys(domains));

    function find(domainInput) {
      const host = psl.cleanHost(domainInput);
      if (!host) return null;
      const labels = host.split('.');
      for (let i = 0; i < labels.length; i += 1) {
        const candidate = labels.slice(i).join('.');
        if (domainKeys.has(candidate)) {
          const rec = domains[candidate];
          return Object.assign({ matchedDomain: candidate }, rec, { companyRecord: companies[rec.companyId] || null });
        }
      }
      return null;
    }

    function sameCompanyAsSite(match, siteDomain) {
      if (!match || !siteDomain) return false;
      const props = (match.companyRecord && match.companyRecord.properties) || [];
      return props.some((property) => {
        const propDomain = psl.registrableDomain(property);
        return propDomain === siteDomain || property === siteDomain;
      });
    }

    return { find, sameCompanyAsSite };
  }
  global.PB = global.PB || {};
  global.PB.Disconnect = { initDisconnect };
})(typeof globalThis !== 'undefined' ? globalThis : self);
