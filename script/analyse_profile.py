
import pstats
p = pstats.Stats('profile.out')
# p.strip_dirs().sort_stats(-1).print_stats()

# p.sort_stats('cumulative').print_stats(20)

p.sort_stats('time').print_stats(40)