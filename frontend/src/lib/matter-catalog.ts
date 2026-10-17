export type MatterCatalogSectionId = "popular" | "life-cycle" | "groups"

export type MatterCatalogCategory = {
  id: string
  label: string
  icon: "shield" | "house" | "badge" | "graduation" | "bus" | "heart" | "baby" | "book" | "briefcase" | "users" | "accessibility" | "scale" | "car" | "globe" | "landmark" | "cross"
  keywords: string[]
}

export const MATTER_CATALOG_SECTIONS: Array<{ id: MatterCatalogSectionId; title: string; categories: MatterCatalogCategory[] }> = [
  {
    id: "popular", title: "热门服务", categories: [
      { id: "social-security", label: "社保", icon: "shield", keywords: ["社会保障", "社保", "养老", "失业", "工伤", "低保"] },
      { id: "household", label: "户政", icon: "house", keywords: ["户口", "户籍", "身份证", "居住证", "集体户"] },
      { id: "professional", label: "职业资格", icon: "badge", keywords: ["职业资格", "资格考试", "注册", "执业"] },
      { id: "education", label: "教育服务", icon: "graduation", keywords: ["教育", "学校", "学位", "学历", "教师", "学生"] },
      { id: "transport", label: "驾驶、行驶", icon: "bus", keywords: ["驾驶", "车辆", "机动车", "运输", "行驶", "车主"] },
      { id: "medical", label: "医保", icon: "cross", keywords: ["医保", "医疗", "就医", "健康", "医院"] },
    ],
  },
  {
    id: "life-cycle", title: "个人生命周期", categories: [
      { id: "birth", label: "出生", icon: "baby", keywords: ["出生", "生育", "新生儿", "出生医学"] },
      { id: "residence", label: "户籍", icon: "house", keywords: ["户口", "户籍", "身份证", "居住证", "集体户"] },
      { id: "schooling", label: "上学", icon: "book", keywords: ["教育", "学校", "入学", "学位", "学历", "教师", "学生"] },
      { id: "employment", label: "工作", icon: "briefcase", keywords: ["就业", "工作", "人才", "劳动", "职工", "创业"] },
      { id: "marriage", label: "婚育", icon: "heart", keywords: ["婚姻", "结婚", "离婚", "生育", "孕", "育儿"] },
      { id: "life-social-security", label: "社保", icon: "shield", keywords: ["社会保障", "社保", "养老", "失业", "工伤", "低保"] },
      { id: "retirement", label: "退休", icon: "users", keywords: ["退休", "养老", "离休", "老年"] },
      { id: "after-life", label: "身后事", icon: "landmark", keywords: ["死亡", "丧葬", "抚恤", "遗属"] },
    ],
  },
  {
    id: "groups", title: "群体服务", categories: [
      { id: "medical-staff", label: "医护人员服务", icon: "cross", keywords: ["医师", "护士", "医疗机构", "医护"] },
      { id: "lawyers", label: "律师服务", icon: "scale", keywords: ["律师", "法律服务", "司法"] },
      { id: "education-group", label: "中高等教育服务", icon: "graduation", keywords: ["中专", "高校", "高等教育", "职业教育", "毕业"] },
      { id: "women-children", label: "妇幼服务", icon: "heart", keywords: ["妇女", "儿童", "母婴", "生育", "孕产"] },
      { id: "elderly", label: "老年人服务", icon: "accessibility", keywords: ["老年", "养老", "退休"] },
      { id: "disabled", label: "助残服务", icon: "accessibility", keywords: ["残疾", "助残", "伤残"] },
      { id: "overseas", label: "港澳台/华侨/外国人服务", icon: "globe", keywords: ["港澳", "台湾", "华侨", "外国人", "出入境"] },
      { id: "car-owner", label: "车主服务", icon: "car", keywords: ["驾驶", "车辆", "机动车", "运输", "行驶", "车主"] },
    ],
  },
]

export type CatalogMatter = { name: string; description?: string | null }

export function categoriesForMatter(matter: CatalogMatter): MatterCatalogCategory[] {
  const source = `${matter.name} ${matter.description ?? ""}`.toLocaleLowerCase("zh-CN")
  return MATTER_CATALOG_SECTIONS.flatMap((section) => section.categories)
    .filter((category) => category.keywords.some((keyword) => source.includes(keyword.toLocaleLowerCase("zh-CN"))))
}

export function categoryById(categoryId: string | null): MatterCatalogCategory | undefined {
  return MATTER_CATALOG_SECTIONS.flatMap((section) => section.categories).find((category) => category.id === categoryId)
}
