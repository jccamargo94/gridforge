def congestion_rent(sol, t):
    return sum(sol.lmp[b][t] * sol.loads[b][t] for b in sol.buses) - sum(
        sol.lmp[sol.gen_zone[g]][t] * sol.dispatch[g][t] for g in sol.dispatch
    )
